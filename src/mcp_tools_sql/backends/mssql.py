"""Microsoft SQL Server database backend."""

from __future__ import annotations

from typing import Any

from mcp_tools_sql.backends.base import DatabaseBackend
from mcp_tools_sql.config.models import ConnectionConfig


class MSSQLBackend(DatabaseBackend):
    """Backend for Microsoft SQL Server via pyodbc."""

    def __init__(self, config: ConnectionConfig) -> None:
        self._config = config

    def connect(self) -> None:
        """Open a connection to SQL Server."""
        raise NotImplementedError

    def close(self) -> None:
        """Close the SQL Server connection."""
        raise NotImplementedError

    def execute_query(
        self, sql: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Execute a SELECT query."""
        raise NotImplementedError

    def execute_update(self, sql: str, params: dict[str, Any] | None = None) -> int:
        """Execute an UPDATE/INSERT."""
        raise NotImplementedError

    def explain(self, sql: str) -> str:
        """Return the query execution plan."""
        raise NotImplementedError

    def read_schemas(self) -> list[str]:
        """List schemas in the database."""
        raise NotImplementedError

    def read_tables(self, schema: str) -> list[str]:
        """List tables in the given schema."""
        raise NotImplementedError

    def read_columns(
        self,
        schema: str,
        table: str,
        filter_pattern: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return column metadata for a table."""
        raise NotImplementedError

    def search_columns(
        self,
        schema: str,
        table: str,
        pattern: str,
    ) -> list[dict[str, Any]]:
        """Search columns by name pattern."""
        raise NotImplementedError

    def read_relations(self, schema: str, table: str) -> list[dict[str, Any]]:
        """Return foreign-key relationships."""
        raise NotImplementedError
