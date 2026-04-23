"""MCP tool server for SQL database access."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

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
    ) -> None:
        self._config = config
        self._backend = backend
        self._mcp: Any = None

    def _register_builtin_tools(self) -> None:
        """Register schema-exploration and validation tools."""
        # TODO: register SchemaTools, ValidationTools
        raise NotImplementedError

    def _register_configured_tools(self) -> None:
        """Register query and update tools from the project config."""
        # TODO: register QueryTools, UpdateTools based on config
        raise NotImplementedError

    def run(self) -> None:
        """Start the MCP server event loop."""
        self._register_builtin_tools()
        self._register_configured_tools()
        # TODO: start the server transport
        raise NotImplementedError


def create_server(
    config: QueryFileConfig,
    backend: DatabaseBackend,
) -> ToolServer:
    """Factory: build and return a configured ToolServer.

    Returns:
        A configured ToolServer instance.
    """
    return ToolServer(config=config, backend=backend)
