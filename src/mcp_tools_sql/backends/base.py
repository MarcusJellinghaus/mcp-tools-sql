"""Abstract base class for database backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import AbstractContextManager
from types import TracebackType
from typing import Any, Self

from mcp_tools_sql.config.models import ConnectionConfig


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
    def execute_update(self, sql: str, params: dict[str, Any] | None = None) -> int:
        """Execute an UPDATE/INSERT and return affected row count.

        Implies connected: backends MUST connect lazily on first call. After
        ``close()``, further calls raise ``RuntimeError``.
        """

    @abstractmethod
    def explain(self, sql: str, params: dict[str, Any] | None = None) -> str:
        """Return the query execution plan as text.

        Implies connected: backends MUST connect lazily on first call. After
        ``close()``, further calls raise ``RuntimeError``.
        """

    @abstractmethod
    def get_isolated_connection(self) -> AbstractContextManager[Any]:
        """Yield a single-use connection.

        SQLite yields the persistent connection (no-op isolation: EXPLAIN QUERY
        PLAN does not execute the statement). MSSQL yields a fresh pyodbc
        connection built from the same ConnectionConfig, closed on context exit.
        Callers MUST NOT close the yielded connection; the backend owns its
        lifecycle.
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


def create_backend(config: ConnectionConfig) -> DatabaseBackend:
    """Factory: instantiate the appropriate backend for *config.backend*.

    Returns:
        A DatabaseBackend instance for the requested backend type.

    Raises:
        ValueError: If the backend type is not supported.
    """
    if config.backend == "sqlite":
        from mcp_tools_sql.backends.sqlite import SQLiteBackend

        return SQLiteBackend(config)
    if config.backend in ("mssql", "pyodbc"):
        from mcp_tools_sql.backends.mssql import MSSQLBackend

        return MSSQLBackend(config)
    msg = f"Unsupported backend: {config.backend}"
    raise ValueError(msg)
