"""MCP tools for database schema exploration."""

from __future__ import annotations

import tomllib
from pathlib import Path

from mcp_tools_sql.config.models import QueryConfig


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
