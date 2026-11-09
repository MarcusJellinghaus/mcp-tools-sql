"""MCP tool server for SQL database access."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from mcp.server.fastmcp import FastMCP

from mcp_tools_sql.config.loader import discover_query_config
from mcp_tools_sql.schema_tools import (
    PROGRAMMATIC_BUILTIN_TOOLS,
    load_default_queries,
)
from mcp_tools_sql.toolset import SqlToolset, build_toolset

if TYPE_CHECKING:
    from mcp_tools_sql.utils.tool_spec import ToolSpec

logger = logging.getLogger(__name__)


class FastMCPSink:
    """ToolSink adapter that registers each spec on a FastMCP instance."""

    def __init__(self, mcp: FastMCP) -> None:
        self._mcp = mcp

    def add(self, spec: ToolSpec) -> None:
        """Register ``spec`` as a FastMCP tool under its name and description."""
        self._mcp.add_tool(spec.fn, name=spec.name, description=spec.description)


class ToolServer:
    """MCP server that exposes a :class:`SqlToolset` to Claude Code."""

    def __init__(self, toolset: SqlToolset) -> None:
        self._toolset = toolset
        self._mcp = FastMCP("mcp-tools-sql")
        sink = FastMCPSink(self._mcp)
        for spec in toolset.specs:
            sink.add(spec)

    @property
    def mcp(self) -> FastMCP:
        """Expose FastMCP instance (for testing)."""
        return self._mcp

    @property
    def toolset(self) -> SqlToolset:
        """Expose the toolset passed to the constructor."""
        return self._toolset

    def run(self) -> None:
        """Start the MCP server event loop."""
        self._mcp.run(transport="stdio")

    def close(self) -> None:
        """Close every backend connection held by the toolset."""
        self._toolset.close()


def build_tool_server(args: argparse.Namespace) -> tuple[ToolServer, Path]:
    """Discover the query config, build the toolset and a registered ToolServer.

    Returns:
        The constructed server and the resolved query config path.
    """
    qpath = discover_query_config(args.config, project_dir=Path.cwd())
    toolset = build_toolset(qpath, args.database_config)
    try:
        server = ToolServer(toolset)
    except BaseException:
        toolset.close()
        raise
    return server, qpath


def run_server(args: argparse.Namespace) -> None:
    """Build the tool server from the configs, then run it.

    Pure wiring: discover the query config, build the toolset (loading both
    configs and resolving every ``(connection, database)`` target), register
    it on the tool server, and invoke its event loop. Raises
    ``ValueError`` / ``OSError`` on pre-``mcp.run()`` configuration failures
    and propagates ``KeyboardInterrupt`` from the event loop.
    ``server.close()`` always runs via ``finally``.
    """
    server, qpath = build_tool_server(args)
    try:
        targets = server.toolset.targets
        n_builtin = len(load_default_queries()) + len(PROGRAMMATIC_BUILTIN_TOOLS)
        logger.info(
            "starting MCP server backend=%s connection=%s "
            "connections=%d databases=%d query_config=%s builtin_tools=%d",
            targets.default.backend_name,
            server.toolset.query_config.connection,
            len(targets.connection_names),
            len(targets.database_names),
            qpath,
            n_builtin,
        )
        server.run()
    finally:
        server.close()
