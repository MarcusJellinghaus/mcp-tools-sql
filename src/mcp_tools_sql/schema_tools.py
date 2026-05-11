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


def register_builtin_tools(
    mcp: FastMCP,
    backend: DatabaseBackend,
    backend_name: str,
) -> None:
    """Load default_queries.toml and register all schema tools on mcp."""
    queries = load_default_queries()
    for name, config in queries.items():
        fn = build_tool_fn(name, config, backend, backend_name)
        mcp.add_tool(fn)
