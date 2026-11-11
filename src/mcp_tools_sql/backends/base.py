"""Abstract base class for database backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Generator
from dataclasses import dataclass
from types import TracebackType
from typing import Any, Self

_SQLITE_INTERRUPT = 9
_SQLSTATE_TIMEOUT = "HYT00"

FETCH_BATCH_SIZE: int = 500


class QueryTimeoutError(Exception):
    """A statement exceeded the connection's query_timeout_seconds."""

    def __init__(self, seconds: int) -> None:
        self.seconds = seconds
        super().__init__(f"Query aborted after {seconds} s (statement timeout).")


class BackendError(Exception):
    """A database driver error translated at the backend boundary.

    Built from the driver exception's ``args``, so ``str()`` is identical.

    Attributes:
        original_class: The driver exception class name, e.g.
            ``"OperationalError"``.
    """

    def __init__(self, *args: object, original_class: str) -> None:
        super().__init__(*args)
        self.original_class = original_class


class BackendConnectionError(BackendError):
    """Driver OperationalError / InterfaceError (connection-shaped)."""


def wrap_driver_error(
    exc: BaseException, connection_types: tuple[type[BaseException], ...]
) -> BackendError:
    """Build the neutral exception for a driver exception.

    Args:
        exc: The exception raised by the driver.
        connection_types: Driver exception types that are connection-shaped.

    Returns:
        A :class:`BackendConnectionError` when *exc* is one of
        *connection_types*, otherwise a plain :class:`BackendError`; either
        keeps *exc*'s ``args`` and class name.
    """
    cls = BackendConnectionError if isinstance(exc, connection_types) else BackendError
    return cls(*exc.args, original_class=type(exc).__name__)


@dataclass
class Deadline:
    """Caller-set counting deadline (time.monotonic()), None = not armed."""

    at: float | None = None


def translate_timeout(exc: BaseException, seconds: int) -> QueryTimeoutError | None:
    """Map a driver timeout error to :class:`QueryTimeoutError`.

    Recognises SQLite's ``SQLITE_INTERRUPT`` (``sqlite_errorcode == 9``) and
    the ODBC statement-timeout SQLSTATE ``HYT00`` (``exc.args[0]``). Reads
    attributes only, so no driver module is imported.

    Args:
        exc: The exception raised by the driver.
        seconds: The statement timeout that was in force.

    Returns:
        A :class:`QueryTimeoutError` when *exc* is a statement timeout,
        otherwise ``None``.
    """
    if getattr(exc, "sqlite_errorcode", None) == _SQLITE_INTERRUPT:
        return QueryTimeoutError(seconds)
    if exc.args and exc.args[0] == _SQLSTATE_TIMEOUT:
        return QueryTimeoutError(seconds)
    return None


# Backend name -> sqlglot dialect; its keys are the supported backends.
_DIALECTS: dict[str, str] = {
    "sqlite": "sqlite",
    "mssql": "tsql",
    "pyodbc": "tsql",
}
SUPPORTED_BACKENDS: frozenset[str] = frozenset(_DIALECTS)
_ALIASES: dict[str, str] = {"pyodbc": "mssql"}


def normalize_backend(name: str) -> str:
    """Map a backend alias to its canonical name (``pyodbc`` -> ``mssql``).

    Args:
        name: The configured backend identifier.

    Returns:
        The canonical backend name; non-alias names are returned unchanged.
    """
    return _ALIASES.get(name, name)


def to_dialect(backend_name: str) -> str:
    """Map a backend name to the sqlglot dialect used for parsing/rendering.

    Args:
        backend_name: The configured backend identifier
            (``"sqlite"``, ``"mssql"``, or ``"pyodbc"``).

    Returns:
        The sqlglot dialect name (``"sqlite"`` or ``"tsql"``).

    Raises:
        ValueError: If ``backend_name`` is not a supported backend.
            Unreachable via the tool call sites (each runs ``create_backend``
            first); kept as defence-in-depth against a future caller.
    """
    dialect = _DIALECTS.get(backend_name)
    if dialect is None:
        raise ValueError(
            f"Unsupported backend: {backend_name}. "
            f"Supported: {', '.join(sorted(_DIALECTS))}."
        )
    return dialect


class DatabaseBackend(ABC):
    """Interface that all database backends must implement."""

    @abstractmethod
    def connect(self) -> None:
        """Open a connection to the database."""

    @abstractmethod
    def close(self) -> None:
        """Close the database connection."""

    @abstractmethod
    def execute_query(
        self, sql: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Execute a SELECT query and return rows as dicts.

        Implies connected: backends MUST connect lazily on first call. After
        ``close()``, further calls raise ``RuntimeError``.
        """

    @abstractmethod
    def execute_readonly_query(
        self, sql: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Execute a SELECT under a DB-enforced read-only guarantee.

        The backstop (Layer 2) for read-only tools: even if the AST gate is
        bypassed, the database itself rejects writes. Semantics are
        asymmetric per backend:

        - SQLite opens a fresh single-use connection with
          ``PRAGMA query_only = ON`` (closed after use), leaving the
          persistent connection untouched.
        - MSSQL delegates to :meth:`execute_query`, relying on a documented
          read-only login (``db_datareader`` + ``db_denydatawriter``).
        - Postgres (future) would issue ``SET TRANSACTION READ ONLY``.

        Implies connected: backends MUST connect lazily on first call. After
        ``close()``, further calls raise ``RuntimeError``.
        """

    @abstractmethod
    def execute_readonly_query_with_columns(
        self, sql: str, params: dict[str, Any] | None = None
    ) -> tuple[list[str], list[tuple[Any, ...]]]:
        """Execute a SELECT read-only, returning column names and raw rows.

        Same DB-enforced read-only guarantee as
        :meth:`execute_readonly_query` (SQLite: a fresh single-use
        ``PRAGMA query_only = ON`` connection; MSSQL: the documented
        read-only login), but the result keeps the projection shape:
        ordered column names plus positional row tuples. Unlike the dict
        form, this preserves duplicate column names — which is why callers
        that need per-ordinal values (the ``summarize`` value probe) use it.

        Implies connected: backends MUST connect lazily on first call. After
        ``close()``, further calls raise ``RuntimeError``.

        Args:
            sql: The SELECT statement to execute.
            params: Optional values for ``:name`` placeholders in *sql*.

        Returns:
            Tuple ``(columns, rows)``: column names in projection order, and
            one plain tuple per row positionally aligned with *columns*. Both
            are empty when the statement produces no result set.
        """

    def iter_readonly_batches(
        self,
        sql: str,
        params: dict[str, Any] | None = None,
        *,
        counting: Deadline | None = None,  # pylint: disable=unused-argument
    ) -> Generator[list[dict[str, Any]], None, None]:
        """Yield read-only result rows in batches.

        Same DB-enforced read-only guarantee as
        :meth:`execute_readonly_query`. This default runs that method and
        slices its result, ignoring *counting*; backends override it to
        fetch with ``cursor.fetchmany`` so only one batch is in memory.

        Callers that stop early MUST close the generator (``gen.close()`` or
        ``contextlib.closing``) so the backend releases its cursor and
        connection. A :class:`QueryTimeoutError` is raised if execute or a
        fetch hit the statement timeout or the counting deadline. After one
        never continue fetching: on SQLite a later ``fetchmany`` returns
        ``[]``, which is indistinguishable from end of data.

        Args:
            sql: The SELECT statement to execute.
            params: Optional values for ``:name`` placeholders in *sql*.
            counting: Optional caller-set counting deadline; backends that
                enforce it interrupt the statement once it passes.

        Yields:
            Non-empty lists of row dicts, each at most ``FETCH_BATCH_SIZE``
            long.
        """
        rows = self.execute_readonly_query(sql, params)
        for start in range(0, len(rows), FETCH_BATCH_SIZE):
            yield rows[start : start + FETCH_BATCH_SIZE]

    @abstractmethod
    def execute_update(self, sql: str, params: dict[str, Any] | None = None) -> int:
        """Execute an UPDATE/INSERT and return affected row count.

        Implies connected: backends MUST connect lazily on first call. After
        ``close()``, further calls raise ``RuntimeError``.
        """

    @abstractmethod
    def explain(
        self, sql: str, params: dict[str, Any] | None = None, *, isolated: bool = False
    ) -> str:
        """Return the query execution plan as text.

        ``isolated``: run on a fresh single-use connection where the backend
        has one (MSSQL), so session state set by the plan request cannot leak
        into the persistent connection; backends without one (SQLite) ignore
        it. Isolated calls skip the closed check where the backend opens a
        fresh connection.

        Implies connected: backends MUST connect lazily on first call. After
        ``close()``, further non-isolated calls raise ``RuntimeError``.
        """

    def __enter__(self) -> Self:
        """Connect and return self for use as context manager.

        Returns:
            Self for use in a ``with`` statement.
        """
        self.connect()
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc_val: BaseException | None,
        _exc_tb: TracebackType | None,
    ) -> None:
        """Close connection on context exit."""
        self.close()
