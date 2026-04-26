"""Abstract base class for database backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
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
        """Execute a SELECT query and return rows as dicts."""

    @abstractmethod
    def execute_update(self, sql: str, params: dict[str, Any] | None = None) -> int:
        """Execute an UPDATE/INSERT and return affected row count."""

    @abstractmethod
    def explain(self, sql: str) -> str:
        """Return the query execution plan as text."""

    @abstractmethod
    def read_schemas(self) -> list[str]:
        """List available schemas in the database."""

    @abstractmethod
    def read_tables(self, schema: str) -> list[str]:
        """List tables in the given schema."""

    @abstractmethod
    def read_columns(
        self,
        schema: str,
        table: str,
        filter_pattern: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return column metadata for a table, optionally filtered."""

    @abstractmethod
    def read_relations(self, schema: str, table: str) -> list[dict[str, Any]]:
        """Return foreign-key relationships for a table."""

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
