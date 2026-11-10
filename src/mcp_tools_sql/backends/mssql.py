"""Microsoft SQL Server database backend."""

from __future__ import annotations

import logging
import sys
import threading
from collections.abc import Generator, Iterator
from contextlib import contextmanager
from typing import Any

from mcp_tools_sql.backends.base import (
    FETCH_BATCH_SIZE,
    BackendError,
    DatabaseBackend,
    Deadline,
    QueryTimeoutError,
    translate_timeout,
    wrap_driver_error,
)
from mcp_tools_sql.config.models import ConnectionConfig
from mcp_tools_sql.sql_ast.placeholders import (
    substitute_named_with_literals,
    translate_named_to_qmark,
)

logger = logging.getLogger(__name__)

_NEEDS_BRACES = set(";={}")


def _odbc_escape(value: str) -> str:
    """Escape an ODBC connection-string value per the ODBC spec.

    Wraps the value in ``{...}`` if it contains ``;``, ``=``, ``{``, ``}``,
    or has surrounding whitespace; embedded ``}`` characters are doubled.

    Returns:
        The escaped value, braced if special characters were present.
    """
    if not value:
        return value
    if any(c in _NEEDS_BRACES for c in value) or value != value.strip():
        return "{" + value.replace("}", "}}") + "}"
    return value


def _build_connection_string(config: ConnectionConfig) -> str:
    r"""Build a pyodbc connection string from a ``ConnectionConfig``.

    A ``port`` of ``0`` (the model default when the TOML key is omitted) is
    treated as "no port specified" — only the host is emitted in the
    ``Server=`` part. This lets ODBC use the SQL Server default (1433) for
    default instances, or query SQL Browser when the host is a named
    instance (``host\instance``).

    Returns:
        A semicolon-joined ``key=value`` string with deterministic ordering.
    """
    server_part = (
        f"Server={config.host},{config.port}"
        if config.port
        else f"Server={config.host}"
    )
    parts = [
        f"Driver={{{config.driver}}}",
        server_part,
        f"Database={_odbc_escape(config.database)}",
    ]
    if config.trusted_connection:
        parts.append("Trusted_Connection=yes")
    else:
        parts.append(f"UID={_odbc_escape(config.username)}")
        parts.append(f"PWD={_odbc_escape(config.password)}")
    parts.append(f"Encrypt={'yes' if config.encrypt else 'no'}")
    parts.append(
        f"TrustServerCertificate={'yes' if config.trust_server_certificate else 'no'}"
    )
    return ";".join(parts)


def _sanitize(msg: str, password: str) -> str:
    """Redact the password from driver text such as ``pyodbc.Error.args``.

    Every password-derived form is redacted: a password containing ``}``
    reaches the driver doubled and braced, so the literal alone does not
    match, and neither does the braced form if the driver echoes only the
    doubled body without its braces.

    Returns:
        The message with every password-derived form replaced by ``***``.
    """
    if not password:
        return msg
    forms = [_odbc_escape(password), password.replace("}", "}}"), password]
    for form in dict.fromkeys(forms):
        msg = msg.replace(form, "***")
    return msg


def build_sanitized_connection_string(config: ConnectionConfig) -> str:
    """Return the full ODBC connection string with the password redacted.

    The real password is never built into the string: the builder is fed a
    copy of the config already carrying the ``***`` placeholder, so nothing
    has to be scrubbed out afterwards. An unset password renders as a bare
    ``PWD=`` so misconfiguration stays visible; for ``trusted_connection``
    no ``PWD=`` part is emitted at all.

    Returns:
        The ODBC connection string suitable for display, with the password
        replaced by ``***``.
    """
    shown = "***" if config.password else ""
    return _build_connection_string(config.model_copy(update={"password": shown}))


def _translate_pyodbc(exc: BaseException) -> BackendError | None:
    """Neutral exception for a pyodbc error, or None if exc is not one.

    Resolves pyodbc via ``sys.modules`` at call time (never imports it), so
    the module stays importable without the driver and works with
    ``fake_pyodbc``.

    Returns:
        A :class:`BackendConnectionError` for ``OperationalError`` /
        ``InterfaceError``, a plain :class:`BackendError` for any other
        ``pyodbc.Error``, otherwise ``None``.
    """
    module = sys.modules.get("pyodbc")
    error_cls = getattr(module, "Error", None)
    if not isinstance(error_cls, type) or not isinstance(exc, error_cls):
        return None
    connection_types = tuple(
        cls
        for cls in (
            getattr(module, "OperationalError", None),
            getattr(module, "InterfaceError", None),
        )
        if isinstance(cls, type)
    )
    return wrap_driver_error(exc, connection_types)


def pyodbc_version() -> str:
    """Return pyodbc's version string; ``ImportError`` if pyodbc is missing.

    Returns:
        ``pyodbc.version``, or ``""`` when the module does not expose one.
    """
    import pyodbc  # pylint: disable=import-error,import-outside-toplevel

    return str(getattr(pyodbc, "version", ""))


def odbc_drivers() -> list[str]:
    """Return the installed ODBC driver names (``pyodbc.drivers()``).

    ``ImportError`` if pyodbc is missing; errors from ``pyodbc.drivers()``
    propagate unchanged.

    Returns:
        The driver names as reported by pyodbc.
    """
    import pyodbc  # pylint: disable=import-error,import-outside-toplevel

    return list(pyodbc.drivers())


class MSSQLBackend(DatabaseBackend):
    """Backend for Microsoft SQL Server via pyodbc.

    Every connection carries a login timeout (``connect_timeout_seconds``) and
    a statement timeout (``query_timeout_seconds``). A ``HYT00`` raised by
    execute/fetch is translated to :class:`QueryTimeoutError`; a ``HYT00``
    from ``connect()`` is a login timeout and becomes
    :class:`BackendConnectionError`. Every other pyodbc error becomes a
    :class:`BackendError` (or :class:`BackendConnectionError`).
    """

    def __init__(self, config: ConnectionConfig) -> None:
        self._config = config
        self._connection: Any = None
        self._closed: bool = False
        self._connect_lock = threading.Lock()

    def _open_connection(self) -> Any:
        """Open a fresh pyodbc connection with the password redacted from errors.

        The single connect path for this backend: it logs the attempt with a
        sanitized connection string and, if pyodbc raises, redacts the password
        from the error's ``args`` in place before raising it as a
        :class:`BackendError` (sqlstate kept in ``args``, driver exception
        chained as ``__cause__``).

        The login timeout is ``connect_timeout_seconds``; a ``HYT00`` raised
        here is a login timeout and becomes :class:`BackendConnectionError`,
        never :class:`QueryTimeoutError`. The statement timeout
        (``query_timeout_seconds``) is set on the returned connection.

        Returns:
            The live pyodbc connection.
        """
        import pyodbc  # pylint: disable=import-error,import-outside-toplevel

        conn_str = _build_connection_string(self._config)
        logger.debug(
            "MSSQL connect attempt: %s",
            build_sanitized_connection_string(self._config),
        )
        try:
            conn = pyodbc.connect(
                conn_str,
                autocommit=True,
                timeout=self._config.connect_timeout_seconds,
            )
            conn.timeout = self._config.query_timeout_seconds
        except pyodbc.Error as exc:
            exc.args = tuple(
                _sanitize(a, self._config.password) if isinstance(a, str) else a
                for a in exc.args
            )
            logger.debug("MSSQL connect failed: %s %r", type(exc).__name__, exc.args)
            neutral = wrap_driver_error(
                exc, (pyodbc.OperationalError, pyodbc.InterfaceError)
            )
            raise neutral from exc
        return conn

    @contextmanager
    def _timeouts(self) -> Iterator[None]:
        """Translate driver errors from cursor/connection work.

        Order: a :class:`BackendError` passes through untouched (a translated
        login ``HYT00`` must not become a statement timeout), a statement
        ``HYT00`` becomes :class:`QueryTimeoutError`, any other pyodbc error
        becomes a neutral :class:`BackendError`; everything else propagates
        unchanged.

        Raises:
            QueryTimeoutError: If the wrapped cursor work hit the statement
                timeout.
        """
        try:
            yield
        except Exception as exc:
            if isinstance(exc, BackendError):
                raise
            seconds = self._config.query_timeout_seconds
            if translate_timeout(exc, seconds) is not None:
                raise QueryTimeoutError(seconds) from exc
            neutral = _translate_pyodbc(exc)
            if neutral is None:
                raise
            raise neutral from exc

    def connect(self) -> None:
        """Open a connection to SQL Server (lazy, idempotent, thread-safe).

        Driver errors arrive translated from :meth:`_open_connection`, with
        the password redacted from ``args``.

        Raises:
            RuntimeError: If the backend was already closed.
        """
        if self._connection is not None and not self._closed:
            return
        with self._connect_lock:
            if self._closed:
                msg = "Backend has been closed."
                raise RuntimeError(msg)
            if self._connection is not None:
                return
            self._connection = self._open_connection()

    def close(self) -> None:
        """Close the SQL Server connection (idempotent)."""
        if self._connection is not None:
            with self._timeouts():
                self._connection.close()
            self._connection = None
        self._closed = True

    def _ensure_connected(self) -> Any:
        """Lazily connect and return the live connection object.

        Returns:
            The active pyodbc connection.

        Raises:
            RuntimeError: If no connection is open after ``connect()``.
        """
        self.connect()
        if self._connection is None:
            msg = "Backend connection is not open."
            raise RuntimeError(msg)
        return self._connection

    def _params_for_pyodbc(
        self, sql: str, params: dict[str, Any] | None
    ) -> tuple[str, list[Any]]:
        """Translate ``:name`` placeholders to ``?`` and build positional args.

        Returns:
            Tuple ``(translated_sql, args)`` where ``args[i]`` corresponds to
            the *i*-th ``?`` in ``translated_sql``.
        """
        sql_q, ordered_names = translate_named_to_qmark(sql, "tsql")
        bound = params or {}
        args = [bound[name] for name in ordered_names]
        return sql_q, args

    def execute_query(
        self, sql: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Execute a SELECT query.

        Returns:
            Rows as a list of column-name keyed dicts.
        """
        conn = self._ensure_connected()
        sql_q, args = self._params_for_pyodbc(sql, params)
        with self._timeouts():
            cursor = conn.cursor()
            try:
                cursor.execute(sql_q, args)
                columns = [d[0] for d in cursor.description]
                rows = cursor.fetchall()
            finally:
                cursor.close()
        return [dict(zip(columns, row, strict=True)) for row in rows]

    def execute_readonly_query(
        self, sql: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Execute a SELECT, delegating to :meth:`execute_query`.

        MSSQL's read-only guarantee comes from a documented read-only login
        (``db_datareader`` + ``db_denydatawriter``), not a per-call session
        setting, so this is a trivial delegation.

        Returns:
            Rows as a list of column-name keyed dicts.
        """
        return self.execute_query(sql, params)

    def iter_readonly_batches(
        self,
        sql: str,
        params: dict[str, Any] | None = None,
        *,
        counting: Deadline | None = None,  # pylint: disable=unused-argument
    ) -> Generator[list[dict[str, Any]], None, None]:
        """Yield rows in batches via ``cursor.fetchmany`` on the persistent connection.

        Read-only by the documented read-only login, like
        :meth:`execute_readonly_query`. Execute and the fetch loop run under
        the connection's statement timeout; *counting* is ignored (the
        caller checks the clock between batches). The cursor is closed in
        ``finally``, so closing the generator early releases it; an early
        close cancels the statement first so the driver does not drain the
        pending rows. A
        :class:`QueryTimeoutError` is raised if execute or a fetch hit the
        statement timeout; never continue fetching after one.

        Args:
            sql: The SELECT statement to execute.
            params: Optional values for ``:name`` placeholders in *sql*.
            counting: Ignored on SQL Server.

        Yields:
            Non-empty lists of column-name keyed dicts, each at most
            ``FETCH_BATCH_SIZE`` long.
        """
        conn = self._ensure_connected()
        sql_q, args = self._params_for_pyodbc(sql, params)
        with self._timeouts():
            cursor = conn.cursor()
            try:
                cursor.execute(sql_q, args)
                columns = [d[0] for d in cursor.description]
                while batch := cursor.fetchmany(FETCH_BATCH_SIZE):
                    yield [dict(zip(columns, row, strict=True)) for row in batch]
            except GeneratorExit:
                # Closed early: cancel so close() does not drain the pending rows.
                try:
                    cursor.cancel()
                except Exception:  # pylint: disable=broad-exception-caught
                    logger.debug("MSSQL cursor cancel failed", exc_info=True)
                raise
            finally:
                cursor.close()

    def execute_readonly_query_with_columns(
        self, sql: str, params: dict[str, Any] | None = None
    ) -> tuple[list[str], list[tuple[Any, ...]]]:
        """Execute a SELECT, returning column names and raw row tuples.

        MSSQL's read-only guarantee comes from a documented read-only login
        (``db_datareader`` + ``db_denydatawriter``), not a per-call session
        setting, so this runs on the persistent connection exactly like
        :meth:`execute_query`. Only the result shape differs: names are taken
        from ``cursor.description`` and rows stay positional, so duplicate
        column names survive instead of collapsing into one dict key.

        Args:
            sql: The SELECT statement to execute.
            params: Optional values for ``:name`` placeholders in *sql*.

        Returns:
            Tuple ``(columns, rows)``: column names in projection order, and
            one plain tuple per row positionally aligned with *columns*.
        """
        conn = self._ensure_connected()
        sql_q, args = self._params_for_pyodbc(sql, params)
        with self._timeouts():
            cursor = conn.cursor()
            try:
                cursor.execute(sql_q, args)
                columns = [d[0] for d in cursor.description or ()]
                rows = cursor.fetchall()
            finally:
                cursor.close()
        return columns, [tuple(row) for row in rows]

    def execute_update(self, sql: str, params: dict[str, Any] | None = None) -> int:
        """Execute an UPDATE/INSERT.

        Returns:
            Number of affected rows.
        """
        conn = self._ensure_connected()
        sql_q, args = self._params_for_pyodbc(sql, params)
        with self._timeouts():
            cursor = conn.cursor()
            try:
                cursor.execute(sql_q, args)
                rowcount = int(cursor.rowcount)
            finally:
                cursor.close()
        return rowcount

    @contextmanager
    def _isolated_connection(self) -> Iterator[Any]:
        """Yield a fresh pyodbc connection, closed on context exit.

        Builds a new connection from the same ``ConnectionConfig`` used by the
        persistent connection, via :meth:`_open_connection` — so it emits the
        same connect-attempt debug line and carries the same password-redaction
        guarantee for driver errors. The fresh connection is closed on context
        exit (success or exception); a close error is translated like any
        other driver error. Callers MUST NOT close the yielded connection.

        Yields:
            The fresh pyodbc connection.
        """
        conn = self._open_connection()
        try:
            yield conn
        finally:
            with self._timeouts():
                conn.close()

    def explain(
        self, sql: str, params: dict[str, Any] | None = None, *, isolated: bool = False
    ) -> str:
        """Return the query execution plan via ``SET SHOWPLAN_TEXT ON``.

        Parameter values are substituted into the SQL as literals before
        enabling SHOWPLAN_TEXT, because pyodbc's prepared-statement protocol
        (used for parameter binding) does not return result rows when
        SHOWPLAN_TEXT is on.

        With ``isolated=True`` the plan runs on a fresh connection from
        :meth:`_isolated_connection` (closed afterwards), so it works even
        after :meth:`close`; literals are substituted before connecting.

        Returns:
            Plain-text execution plan; empty string if MSSQL produces no
            plan rows.
        """
        if isolated:
            explain_sql = substitute_named_with_literals(sql, params or {}, "tsql")
            with self._isolated_connection() as conn:
                return self._showplan(conn, explain_sql)
        conn = self._ensure_connected()
        explain_sql = substitute_named_with_literals(sql, params or {}, "tsql")
        return self._showplan(conn, explain_sql)

    def _showplan(self, conn: Any, explain_sql: str) -> str:
        """Run *explain_sql* on *conn* between SHOWPLAN_TEXT ON and OFF.

        Returns:
            The non-empty first-column plan rows joined by newlines.
        """
        with self._timeouts():
            cursor = conn.cursor()
            try:
                cursor.execute("SET SHOWPLAN_TEXT ON")
                try:
                    cursor.execute(explain_sql)
                    rows = cursor.fetchall()
                finally:
                    cursor.execute("SET SHOWPLAN_TEXT OFF")
            finally:
                cursor.close()
        return "\n".join(r[0] for r in rows if r and r[0])
