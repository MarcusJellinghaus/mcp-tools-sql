"""Microsoft SQL Server database backend."""

from __future__ import annotations

import threading
from typing import Any

from mcp_tools_sql.backends.base import DatabaseBackend
from mcp_tools_sql.config.models import ConnectionConfig
from mcp_tools_sql.utils.sql_placeholders import translate_named_to_qmark

_NEEDS_BRACES = set(";={}")
_DEFAULT_MSSQL_PORT = 1433


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
    """Build a pyodbc connection string from a ``ConnectionConfig``.

    ``port`` of 0 maps to the SQL Server default 1433.

    Returns:
        A semicolon-joined ``key=value`` string with deterministic ordering.
    """
    port = config.port or _DEFAULT_MSSQL_PORT
    parts = [
        f"Driver={{{config.driver}}}",
        f"Server={config.host},{port}",
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
    """Redact the password from a connection-error message.

    Returns:
        The message with any occurrence of ``password`` replaced by ``***``.
    """
    if password:
        return msg.replace(password, "***")
    return msg


class MSSQLBackend(DatabaseBackend):
    """Backend for Microsoft SQL Server via pyodbc."""

    def __init__(self, config: ConnectionConfig) -> None:
        self._config = config
        self._connection: Any = None
        self._closed: bool = False
        self._connect_lock = threading.Lock()

    def connect(self) -> None:
        """Open a connection to SQL Server (lazy, idempotent, thread-safe).

        If pyodbc raises during ``connect()``, the password is redacted from
        the error message and the original exception is preserved via
        ``raise ... from exc``.

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
            import pyodbc  # pylint: disable=import-error,import-outside-toplevel

            conn_str = _build_connection_string(self._config)
            try:
                self._connection = pyodbc.connect(conn_str, autocommit=True)
            except pyodbc.Error as exc:
                sanitized = _sanitize(str(exc), self._config.password)
                raise type(exc)(sanitized) from exc

    def close(self) -> None:
        """Close the SQL Server connection (idempotent)."""
        if self._connection is not None:
            self._connection.close()
            self._connection = None
        self._closed = True

    def _ensure_connected(self) -> Any:
        """Lazily connect and return the live connection object.

        Returns:
            The active pyodbc connection.
        """
        self.connect()
        assert self._connection is not None
        return self._connection

    def _params_for_pyodbc(
        self, sql: str, params: dict[str, Any] | None
    ) -> tuple[str, list[Any]]:
        """Translate ``:name`` placeholders to ``?`` and build positional args.

        Returns:
            Tuple ``(translated_sql, args)`` where ``args[i]`` corresponds to
            the *i*-th ``?`` in ``translated_sql``.
        """
        sql_q, ordered_names = translate_named_to_qmark(sql)
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
        cursor = conn.cursor()
        try:
            cursor.execute(sql_q, args)
            columns = [d[0] for d in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
        finally:
            cursor.close()

    def execute_update(self, sql: str, params: dict[str, Any] | None = None) -> int:
        """Execute an UPDATE/INSERT.

        Returns:
            Number of affected rows.
        """
        conn = self._ensure_connected()
        sql_q, args = self._params_for_pyodbc(sql, params)
        cursor = conn.cursor()
        try:
            cursor.execute(sql_q, args)
            return int(cursor.rowcount)
        finally:
            cursor.close()

    def explain(self, sql: str, params: dict[str, Any] | None = None) -> str:
        """Return the query execution plan via ``SET SHOWPLAN_TEXT ON``."""
        conn = self._ensure_connected()
        sql_q, args = self._params_for_pyodbc(sql, params)
        cursor = conn.cursor()
        try:
            cursor.execute("SET SHOWPLAN_TEXT ON")
            try:
                cursor.execute(sql_q, args)
                rows = cursor.fetchall()
            finally:
                cursor.execute("SET SHOWPLAN_TEXT OFF")
            return "\n".join(r[0] for r in rows if r and r[0])
        finally:
            cursor.close()
