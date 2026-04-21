"""MCP tools for executing pre-approved updates."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mcp_tools_sql.backends.base import DatabaseBackend
    from mcp_tools_sql.config.models import UpdateConfig


class UpdateTools:
    """Registers configured update tools on an MCP server."""

    def __init__(self, backend: DatabaseBackend, updates: list[UpdateConfig]) -> None:
        self._backend = backend
        self._updates = updates

    def register(self, mcp: Any) -> None:
        """Register one MCP tool per configured update."""
        # TODO: iterate self._updates, register each as a tool
        _ = mcp
        raise NotImplementedError
