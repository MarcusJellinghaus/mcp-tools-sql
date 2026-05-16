"""MCP tool server for SQL database access."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from mcp.server.fastmcp import FastMCP

from mcp_tools_sql.backends.base import create_backend
from mcp_tools_sql.config.loader import (
    discover_query_config,
    load_database_config,
    load_query_config,
    resolve_connection,
)
from mcp_tools_sql.query_tools import QueryTools
from mcp_tools_sql.schema_tools import (
    _PROGRAMMATIC_BUILTIN_TOOLS,
    SchemaTools,
    load_default_queries,
)
from mcp_tools_sql.update_tools import UpdateTools
from mcp_tools_sql.validation_tools import ValidationTools

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
        allow_updates: bool,
    ) -> None:
        self._config = config
        self._backend = backend
        self._backend_name = backend_name
        self._allow_updates = allow_updates
        self._mcp = FastMCP("mcp-tools-sql")

    @property
    def mcp(self) -> FastMCP:
        """Expose FastMCP instance (for testing)."""
        return self._mcp

    def _register_builtin_tools(self) -> None:
        """Register schema-exploration tools from default_queries.toml and built-in validation tools."""
        SchemaTools(self._backend, self._backend_name).register(self._mcp)
        ValidationTools(self._backend, self._backend_name).register(self._mcp)

    def _register_configured_tools(self) -> None:
        QueryTools(self._backend, self._config.queries, self._backend_name).register(
            self._mcp
        )
        if self._allow_updates:
            UpdateTools(
                self._backend, self._config.updates, self._backend_name
            ).register(self._mcp)

    def run(self) -> None:
        """Start the MCP server event loop."""
        self._register_builtin_tools()
        self._register_configured_tools()
        self._mcp.run(transport="stdio")


def create_server(
    config: QueryFileConfig,
    backend: DatabaseBackend,
    backend_name: str,
    allow_updates: bool,
) -> ToolServer:
    """Factory: build and return a configured ToolServer.

    Returns:
        A configured ToolServer instance.
    """
    return ToolServer(
        config=config,
        backend=backend,
        backend_name=backend_name,
        allow_updates=allow_updates,
    )


def run_server(args: argparse.Namespace) -> None:
    """Wire configs, backend and tool server together, then run.

    Pure wiring: discover and load configs, build a backend, construct the
    tool server, and invoke its event loop. Raises ``ValueError`` /
    ``OSError`` on pre-``mcp.run()`` configuration failures and propagates
    ``KeyboardInterrupt`` from the event loop. ``backend.close()`` always
    runs via ``finally``.
    """
    qpath = discover_query_config(args.config, project_dir=Path.cwd())
    qcfg = load_query_config(qpath)
    dbcfg = load_database_config(args.database_config)
    conn = resolve_connection(qcfg, dbcfg)
    backend = create_backend(conn)
    try:
        n_builtin = len(load_default_queries()) + len(_PROGRAMMATIC_BUILTIN_TOOLS)
        logger.info(
            "starting MCP server backend=%s connection=%s "
            "query_config=%s builtin_tools=%d",
            conn.backend,
            qcfg.connection,
            qpath,
            n_builtin,
        )
        ToolServer(qcfg, backend, conn.backend, dbcfg.security.allow_updates).run()
    finally:
        backend.close()
