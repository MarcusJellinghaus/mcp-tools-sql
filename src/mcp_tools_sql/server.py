"""MCP tool server for SQL database access."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from mcp.server.fastmcp import FastMCP

from mcp_tools_sql.backends.registry import BackendRegistry
from mcp_tools_sql.config.loader import (
    discover_query_config,
    load_database_config,
    load_query_config,
    resolve_targets,
)
from mcp_tools_sql.count_tools import CountTools
from mcp_tools_sql.query_tools import QueryTools
from mcp_tools_sql.schema_tools import (
    PROGRAMMATIC_BUILTIN_TOOLS,
    SchemaTools,
    build_read_databases_tool,
    load_default_queries,
)
from mcp_tools_sql.update_tools import UpdateTools
from mcp_tools_sql.validation_tools import ValidationTools

if TYPE_CHECKING:
    from mcp_tools_sql.config.models import QueryFileConfig, ResolvedTargets

logger = logging.getLogger(__name__)

_READ_DATABASES_DESC = (
    "List the (connection, database) targets configured for this server, with "
    "their backend, description, and which one is the default. This reports the "
    "*configured* targets from the server config — not a live `sys.databases` "
    "listing — so a database missing here means it is not configured, not that "
    "it does not exist."
)


class ToolServer:
    """MCP server that exposes SQL tools to Claude Code."""

    def __init__(
        self,
        config: QueryFileConfig,
        targets: ResolvedTargets,
        registry: BackendRegistry,
        allow_updates: bool,
    ) -> None:
        self._config = config
        self._targets = targets
        self._registry = registry
        self._allow_updates = allow_updates
        self._mcp = FastMCP("mcp-tools-sql")

    @property
    def mcp(self) -> FastMCP:
        """Expose FastMCP instance (for testing)."""
        return self._mcp

    def _register_builtin_tools(self) -> None:
        """Register schema-exploration tools from default_queries.toml and built-in validation tools."""
        SchemaTools(self._registry, self._targets).register(self._mcp)
        ValidationTools(self._registry, self._targets).register(self._mcp)
        CountTools(self._registry, self._targets).register(self._mcp)
        if self._targets.is_multi:
            self._mcp.add_tool(
                build_read_databases_tool(self._targets),
                name="read_databases",
                description=_READ_DATABASES_DESC,
            )

    def _register_configured_tools(self) -> None:
        QueryTools(self._registry, self._targets, self._config.queries).register(
            self._mcp
        )
        if self._allow_updates:
            UpdateTools(self._registry, self._targets, self._config.updates).register(
                self._mcp
            )

    def run(self) -> None:
        """Start the MCP server event loop."""
        self._register_builtin_tools()
        self._register_configured_tools()
        self._mcp.run(transport="stdio")


def create_server(
    config: QueryFileConfig,
    targets: ResolvedTargets,
    registry: BackendRegistry,
    allow_updates: bool,
) -> ToolServer:
    """Factory: build and return a configured ToolServer.

    Returns:
        A configured ToolServer instance.
    """
    return ToolServer(
        config=config,
        targets=targets,
        registry=registry,
        allow_updates=allow_updates,
    )


def run_server(args: argparse.Namespace) -> None:
    """Wire configs, registry and tool server together, then run.

    Pure wiring: discover and load configs, resolve every
    ``(connection, database)`` target, build a :class:`BackendRegistry`,
    construct the tool server, and invoke its event loop. Raises
    ``ValueError`` / ``OSError`` on pre-``mcp.run()`` configuration failures
    and propagates ``KeyboardInterrupt`` from the event loop.
    ``registry.close_all()`` always runs via ``finally``.
    """
    qpath = discover_query_config(args.config, project_dir=Path.cwd())
    qcfg = load_query_config(qpath)
    dbcfg = load_database_config(args.database_config)
    targets = resolve_targets(qcfg, dbcfg)
    registry = BackendRegistry()
    try:
        n_builtin = len(load_default_queries()) + len(PROGRAMMATIC_BUILTIN_TOOLS)
        logger.info(
            "starting MCP server backend=%s connection=%s "
            "connections=%d databases=%d query_config=%s builtin_tools=%d",
            targets.default.backend_name,
            qcfg.connection,
            len(targets.connection_names),
            len(targets.database_names),
            qpath,
            n_builtin,
        )
        ToolServer(qcfg, targets, registry, dbcfg.security.allow_updates).run()
    finally:
        registry.close_all()
