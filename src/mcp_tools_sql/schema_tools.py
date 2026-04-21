"""MCP tools for database schema exploration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mcp_tools_sql.backends.base import DatabaseBackend


class SchemaTools:
    """Registers schema-browsing tools on an MCP server."""

    def __init__(self, backend: DatabaseBackend) -> None:
        self._backend = backend

    def register(self, mcp: Any) -> None:
        """Register schema tools (read_schemas, read_tables, read_columns, etc.)."""
        # TODO: register individual tool handlers
        _ = mcp
        raise NotImplementedError
