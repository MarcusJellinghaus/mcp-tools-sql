"""MCP tool server for SQL database access."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from mcp.server.fastmcp import FastMCP

from mcp_tools_sql.schema_tools import register_builtin_tools

if TYPE_CHECKING:
    from mcp_tools_sql.backends.base import DatabaseBackend
    from mcp_tools_sql.config.models import QueryFileConfig

logger = logging.getLogger(__name__)


class ToolServer:
    """MCP server that exposes SQL tools to Claude Code."""

    def __init__(
        self,
        config: QueryFileConfig,
        backend: DatabaseBackend,
        backend_name: str,
    ) -> None:
        self._config = config
        self._backend = backend
        self._backend_name = backend_name
        self._mcp = FastMCP("mcp-tools-sql")

    @property
    def mcp(self) -> FastMCP:
        """Expose FastMCP instance (for testing)."""
        return self._mcp

    def _register_builtin_tools(self) -> None:
        """Register schema-exploration tools from default_queries.toml."""
        register_builtin_tools(self._mcp, self._backend, self._backend_name)

    def _register_configured_tools(self) -> None:
        # TODO: issue #5
        pass

    def run(self) -> None:
        """Start the MCP server event loop."""
        self._register_builtin_tools()
        self._register_configured_tools()
        self._mcp.run(transport="stdio")


def create_server(
    config: QueryFileConfig,
    backend: DatabaseBackend,
    backend_name: str,
) -> ToolServer:
    """Factory: build and return a configured ToolServer.

    Returns:
        A configured ToolServer instance.
    """
    return ToolServer(config=config, backend=backend, backend_name=backend_name)
