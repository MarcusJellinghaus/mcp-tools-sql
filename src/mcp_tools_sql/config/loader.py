"""Configuration loading and resolution."""

from __future__ import annotations

from pathlib import Path

from mcp_tools_sql.config.models import ConnectionConfig, QueryFileConfig, UserConfig


def load_query_config(path: Path) -> QueryFileConfig:
    """Load and validate the project query configuration file."""
    # TODO: read YAML/TOML, parse into QueryFileConfig
    _ = path
    raise NotImplementedError


def load_user_config(path: Path | None) -> UserConfig:
    """Load user-level configuration, or return defaults if *path* is None."""
    # TODO: read YAML/TOML, parse into UserConfig
    _ = path
    raise NotImplementedError


def resolve_connection(
    query_config: QueryFileConfig,
    user_config: UserConfig,
) -> ConnectionConfig:
    """Merge project and user configs to produce a final ConnectionConfig."""
    # TODO: overlay user credentials onto project connection settings
    _ = query_config, user_config
    raise NotImplementedError
