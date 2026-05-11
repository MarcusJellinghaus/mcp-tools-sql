"""MCP tools for database schema exploration."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import TYPE_CHECKING

from mcp_tools_sql.config.models import QueryConfig
from mcp_tools_sql.tool_builder import build_tool_fn

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from mcp_tools_sql.backends.base import DatabaseBackend


def load_default_queries() -> dict[str, QueryConfig]:
    """Load built-in schema queries from default_queries.toml.

    Returns:
        Dict mapping query name to QueryConfig.
    """
    toml_path = Path(__file__).parent / "default_queries.toml"
    with open(toml_path, "rb") as f:
        data = tomllib.load(f)
    return {
        name: QueryConfig.model_validate(cfg) for name, cfg in data["queries"].items()
    }


class SchemaTools:
    """Registers built-in schema-exploration tools on an MCP server."""

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
            fn = build_tool_fn(
                name,
                config,
                self._backend,
                self._backend_name,
                truncation_hint="Use filter to narrow.",
            )
            mcp.add_tool(fn)
