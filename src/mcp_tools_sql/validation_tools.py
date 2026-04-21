"""MCP tools for SQL validation and dry-run execution."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mcp_tools_sql.backends.base import DatabaseBackend


class ValidationTools:
    """Registers validation tools (explain, dry-run) on an MCP server."""

    def __init__(self, backend: DatabaseBackend) -> None:
        self._backend = backend

    def register(self, mcp: Any) -> None:
        """Register validation tools (explain_query, etc.)."""
        # TODO: register explain and dry-run handlers
        _ = mcp
        raise NotImplementedError
