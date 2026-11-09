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
from mcp_tools_sql.summarize import SummarizeTools
from mcp_tools_sql.tool_logging import log_tool_call
from mcp_tools_sql.update_tools import UpdateTools
from mcp_tools_sql.validation_tools import ValidationTools
from mcp_tools_sql.verification import verify_all
from mcp_tools_sql.verification.render import render_short

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from mcp_tools_sql.config.models import QueryFileConfig, ResolvedTargets

logger = logging.getLogger(__name__)

_READ_DATABASES_DESC = (
    "List the (connection, database) targets configured for this server, with "
    "their backend, description, and which one is the default. This reports the "
    "*configured* targets from the server config — not a live `sys.databases` "
    "listing — so a database missing here means it is not configured, not that "
    "it does not exist."
)

_VERIFY_DESC = (
    "Re-run the `mcp-tools-sql verify` checks against the config files on disk: config "
    "parse, dependencies, connectivity of every configured connection, EXPLAIN of every "
    "configured query, update tables/columns. Returns a short summary plus every failing "
    "or warning row. Use it after a query fails to check config and connectivity. Takes "
    "a few seconds."
)

_RESTART_NOTE = (
    "Note: verify re-read the config files from disk; this server keeps using the config "
    "it loaded at startup. Config edits need a server restart to take effect."
)


class ToolServer:
    """MCP server that exposes SQL tools to Claude Code."""

    def __init__(
        self,
        config: QueryFileConfig,
        targets: ResolvedTargets,
        registry: BackendRegistry,
        allow_updates: bool,
        *,
        query_config_path: Path | None = None,
        database_config_path: Path | None = None,
    ) -> None:
        self._config = config
        self._targets = targets
        self._registry = registry
        self._allow_updates = allow_updates
        self._query_config_path = query_config_path
        self._database_config_path = database_config_path
        self._mcp = FastMCP("mcp-tools-sql")

    @property
    def mcp(self) -> FastMCP:
        """Expose FastMCP instance (for testing)."""
        return self._mcp

    @property
    def config(self) -> QueryFileConfig:
        """Expose the query file config passed to the constructor."""
        return self._config

    @property
    def targets(self) -> ResolvedTargets:
        """Expose the resolved targets passed to the constructor."""
        return self._targets

    def _register_builtin_tools(self) -> None:
        """Register schema-exploration tools from default_queries.toml and built-in validation tools."""
        SchemaTools(self._registry, self._targets, limits=self._config.limits).register(
            self._mcp
        )
        ValidationTools(self._registry, self._targets).register(self._mcp)
        CountTools(self._registry, self._targets).register(self._mcp)
        SummarizeTools(self._registry, self._targets).register(self._mcp)
        if self._targets.is_multi:
            self._mcp.add_tool(
                build_read_databases_tool(self._targets),
                name="read_databases",
                description=_READ_DATABASES_DESC,
            )
        self._mcp.add_tool(
            self._build_verify_tool(), name="verify", description=_VERIFY_DESC
        )

    def _build_verify_tool(self) -> Callable[[], Awaitable[str]]:
        """Build the ``verify`` tool over the config paths given at construction.

        The tool re-reads the configs from disk with its own backend registry;
        it never touches the server's registry. ``None`` paths fall back to
        the same discovery ``verify_all`` uses.

        Returns:
            An async callable returning the short verify summary.
        """
        qpath = self._query_config_path
        dbpath = self._database_config_path

        async def verify() -> str:
            """Re-run the verify checks and return the short summary.

            Returns:
                The short summary followed by the restart note.
            """
            async with log_tool_call("verify"):
                result = verify_all(qpath, dbpath)
            return f"{render_short(result)}\n\n{_RESTART_NOTE}"

        return verify

    def _register_configured_tools(self) -> None:
        QueryTools(
            self._registry,
            self._targets,
            self._config.queries,
            limits=self._config.limits,
        ).register(self._mcp)
        if self._allow_updates:
            UpdateTools(self._registry, self._targets, self._config.updates).register(
                self._mcp
            )

    def register_all(self) -> None:
        """Register every builtin and configured tool."""
        self._register_builtin_tools()
        self._register_configured_tools()

    def run(self) -> None:
        """Start the MCP server event loop."""
        self.register_all()
        self._mcp.run(transport="stdio")

    def close(self) -> None:
        """Close every backend connection held by the registry."""
        self._registry.close_all()


def create_server(
    config: QueryFileConfig,
    targets: ResolvedTargets,
    registry: BackendRegistry,
    allow_updates: bool,
    *,
    query_config_path: Path | None = None,
    database_config_path: Path | None = None,
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
        query_config_path=query_config_path,
        database_config_path=database_config_path,
    )


def build_tool_server(args: argparse.Namespace) -> tuple[ToolServer, Path]:
    """Discover and load configs, then construct an unregistered ToolServer.

    Returns:
        The constructed server and the resolved query config path.
    """
    qpath = discover_query_config(args.config, project_dir=Path.cwd())
    qcfg = load_query_config(qpath)
    dbcfg = load_database_config(args.database_config)
    targets = resolve_targets(qcfg, dbcfg)
    registry = BackendRegistry()
    server = ToolServer(
        qcfg,
        targets,
        registry,
        dbcfg.security.allow_updates,
        query_config_path=qpath,
        database_config_path=args.database_config,
    )
    return server, qpath


def run_server(args: argparse.Namespace) -> None:
    """Wire configs, registry and tool server together, then run.

    Pure wiring: discover and load configs, resolve every
    ``(connection, database)`` target, build a :class:`BackendRegistry`,
    construct the tool server, and invoke its event loop. Raises
    ``ValueError`` / ``OSError`` on pre-``mcp.run()`` configuration failures
    and propagates ``KeyboardInterrupt`` from the event loop.
    ``server.close()`` always runs via ``finally``.
    """
    server, qpath = build_tool_server(args)
    try:
        n_builtin = len(load_default_queries()) + len(PROGRAMMATIC_BUILTIN_TOOLS)
        logger.info(
            "starting MCP server backend=%s connection=%s "
            "connections=%d databases=%d query_config=%s builtin_tools=%d",
            server.targets.default.backend_name,
            server.config.connection,
            len(server.targets.connection_names),
            len(server.targets.database_names),
            qpath,
            n_builtin,
        )
        server.run()
    finally:
        server.close()
