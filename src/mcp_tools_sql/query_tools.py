"""MCP tools for executing pre-approved queries."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mcp_tools_sql.backends.base import DatabaseBackend
    from mcp_tools_sql.config.models import QueryConfig


class QueryTools:
    """Registers configured query tools on an MCP server."""

    def __init__(self, backend: DatabaseBackend, queries: list[QueryConfig]) -> None:
        self._backend = backend
        self._queries = queries

    def register(self, mcp: Any) -> None:
        """Register one MCP tool per configured query."""
        # TODO: iterate self._queries, register each as a tool
        _ = mcp
        raise NotImplementedError
