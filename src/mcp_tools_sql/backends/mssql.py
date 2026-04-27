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
