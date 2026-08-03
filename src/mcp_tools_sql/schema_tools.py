"""MCP tools for database schema exploration."""

from __future__ import annotations

import logging
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING

from mcp_tools_sql.config.models import QueryConfig
from mcp_tools_sql.formatting import format_rows
from mcp_tools_sql.query_helpers import (
    build_query_sig_params,
    build_schema_body,
    build_target_params,
)
from mcp_tools_sql.tool_builder import build_tool_fn

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from mcp.server.fastmcp import FastMCP

    from mcp_tools_sql.backends.registry import BackendRegistry
    from mcp_tools_sql.config.models import ResolvedTargets

logger = logging.getLogger(__name__)

PROGRAMMATIC_BUILTIN_TOOLS: tuple[str, ...] = ("validate_sql", "count_records")


def load_default_queries(path: Path | None = None) -> dict[str, QueryConfig]:
    """Load built-in schema queries from default_queries.toml.

    Args:
        path: Optional path to the TOML file. Defaults to the bundled
            ``default_queries.toml`` next to this module.

    Returns:
        Dict mapping query name to QueryConfig. Entries whose names collide
        with :data:`PROGRAMMATIC_BUILTIN_TOOLS` are skipped with a warning.
    """
    toml_path = (
        path if path is not None else Path(__file__).parent / "default_queries.toml"
    )
    with open(toml_path, "rb") as f:
        data = tomllib.load(f)
    result: dict[str, QueryConfig] = {}
    for name, cfg in data["queries"].items():
        if name in PROGRAMMATIC_BUILTIN_TOOLS:
            logger.warning(
                "Skipping TOML query %r — name reserved by programmatic builtin",
                name,
            )
            continue
        result[name] = QueryConfig.model_validate(cfg)
    return result


def build_read_databases_tool(
    targets: ResolvedTargets,
) -> Callable[[], Awaitable[str]]:
    """Build the config-only ``read_databases`` tool over *targets*.

    The returned async tool tabulates every configured
    ``(connection, database)`` target — ``connection``, ``database``,
    ``backend``, ``description`` (the database description, falling back to the
    connection description), and ``is_default`` — in config order. It reads only
    the resolved config and never touches a backend.

    Returns:
        An async callable rendering the configured targets as a table.
    """
    rows = [
        {
            "connection": t.connection,
            "database": t.database,
            "backend": t.backend_name,
            "description": t.database_description or t.connection_description,
            "is_default": t.is_default,
        }
        for t in targets.targets
    ]

    async def read_databases() -> str:
        """List the configured (connection, database) targets."""
        return format_rows(rows, max_rows=len(rows))

    return read_databases


class SchemaTools:
    """Registers built-in schema-exploration tools on an MCP server."""

    _TRUNCATION_HINT = "Use filter to narrow."

    def __init__(
        self,
        registry: BackendRegistry,
        targets: ResolvedTargets,
    ) -> None:
        self._registry = registry
        self._targets = targets

    def register(self, mcp: FastMCP) -> None:
        """Load default_queries.toml and register all schema tools on ``mcp``.

        Each tool resolves its ``(connection, database)`` target at call time
        (single target for now — fan-out is Step 11). For single-target installs
        ``build_target_params`` adds nothing, so the signature is byte-identical
        to a pinned build.
        """
        for name, config in load_default_queries().items():
            sig_params = build_query_sig_params(config) + build_target_params(
                self._targets
            )
            body = build_schema_body(
                name,
                config,
                self._registry,
                self._targets,
                self._TRUNCATION_HINT,
            )
            fn = build_tool_fn(name, sig_params, body, config.description)
            mcp.add_tool(fn)
