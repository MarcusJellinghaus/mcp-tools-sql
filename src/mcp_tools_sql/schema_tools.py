"""MCP tools for database schema exploration."""

from __future__ import annotations

import logging
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING

from mcp_tools_sql.config.models import QueryConfig
from mcp_tools_sql.query_helpers import build_query_body, build_query_sig_params
from mcp_tools_sql.tool_builder import build_tool_fn

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from mcp_tools_sql.backends.base import DatabaseBackend

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


class SchemaTools:
    """Registers built-in schema-exploration tools on an MCP server."""

    _TRUNCATION_HINT = "Use filter to narrow."

    def __init__(
        self,
        backend: DatabaseBackend,
        backend_name: str,
    ) -> None:
        self._backend = backend
        self._backend_name = backend_name

    def register(self, mcp: FastMCP) -> None:
        """Load default_queries.toml and register all schema tools on ``mcp``."""
        for name, config in load_default_queries().items():
            sig_params = build_query_sig_params(config)
            body = build_query_body(
                name,
                config,
                self._backend,
                self._backend_name,
                self._TRUNCATION_HINT,
            )
            fn = build_tool_fn(name, sig_params, body, config.description)
            mcp.add_tool(fn)
