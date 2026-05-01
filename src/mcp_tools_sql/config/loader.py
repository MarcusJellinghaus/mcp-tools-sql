"""Configuration loading and resolution."""

from __future__ import annotations

import logging
import tomllib
from pathlib import Path

from mcp_tools_sql.config.models import (
    ConnectionConfig,
    DatabaseConfig,
    QueryFileConfig,
)

_SENSITIVE_KEYS = {"password", "connection_string", "credential_env_var"}
_logger = logging.getLogger(__name__)


def _has_sensitive_keys(data: dict[str, object]) -> list[str]:
    """Recursively scan a parsed TOML dict for sensitive keys.

    Returns:
        List of sensitive key names found in the data.
    """
    found: list[str] = []
    for key, value in data.items():
        if key in _SENSITIVE_KEYS:
            found.append(key)
        if isinstance(value, dict):
            found.extend(_has_sensitive_keys(value))
    return found


def _read_toml(path: Path) -> dict[str, object]:
    """Read and parse a TOML file, wrapping errors in ValueError.

    Returns:
        Parsed TOML data as a dictionary.

    Raises:
        ValueError: If the file cannot be read or contains invalid TOML.
    """
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except tomllib.TOMLDecodeError as exc:
        msg = f"Invalid TOML in {path}"
        lineno = getattr(exc, "lineno", None)
        colno = getattr(exc, "colno", None)
        if lineno is not None:
            msg += f" (line {lineno}, col {colno})"
        msg += f": {exc}"
        if "\\" in str(path):
            msg += " (Tip: use forward slashes in TOML file paths)"
        raise ValueError(msg) from exc
    except OSError as exc:
        raise ValueError(f"Cannot read {path}: {exc}") from exc


def load_query_config(path: Path) -> QueryFileConfig:
    """Load and validate the project query configuration file.

    Returns:
        Validated query file configuration.

    Raises:
        ValueError: If the file does not exist or contains invalid data.
    """
    if not path.exists():
        msg = f"Cannot read {path}: file does not exist"
        raise ValueError(msg)

    data = _read_toml(path)

    sensitive = _has_sensitive_keys(data)
    if sensitive:
        keys_str = ", ".join(sorted(sensitive))
        _logger.warning(
            "Query config %s contains sensitive key(s): %s. "
            "Move credentials to database config (~/.mcp-tools-sql/config.toml).",
            path,
            keys_str,
        )

    return QueryFileConfig.model_validate(data)


def load_database_config(path: Path | None = None) -> DatabaseConfig:
    """Load database config from path or default location.

    Returns defaults if the file does not exist. No side effects.

    Returns:
        Database configuration loaded from file or defaults.
    """
    if path is None:
        path = Path.home() / ".mcp-tools-sql" / "config.toml"

    if not path.exists():
        return DatabaseConfig()

    data = _read_toml(path)
    return DatabaseConfig.model_validate(data)


def resolve_connection(
    query_config: QueryFileConfig,
    db_config: DatabaseConfig,
) -> ConnectionConfig:
    """Look up the named connection from database config.

    Returns:
        The resolved connection configuration.

    Raises:
        ValueError: If the connection name is missing or not found
            in db_config.connections.
    """
    name = query_config.connection
    if not name:
        msg = "No connection name specified in query config"
        raise ValueError(msg)
    if name not in db_config.connections:
        available = list(db_config.connections.keys())
        msg = f"Connection '{name}' not found. Available: {available}"
        raise ValueError(msg)
    return db_config.connections[name]


def discover_query_config(
    config_flag: Path | None,
    project_dir: Path,
) -> Path:
    """Find the query config file.

    Discovery chain:
    1. Explicit --config flag path
    2. mcp-tools-sql.toml in project_dir
    3. Raise ValueError with guidance

    Returns:
        Path to the discovered query config file.

    Raises:
        ValueError: If no config file can be found.
    """
    if config_flag is not None:
        if not config_flag.exists():
            msg = f"Config not found: {config_flag}"
            raise ValueError(msg)
        return config_flag
    candidate = project_dir / "mcp-tools-sql.toml"
    if candidate.exists():
        return candidate
    msg = (
        f"No mcp-tools-sql.toml found in {project_dir}. "
        "Use --config or create the file."
    )
    raise ValueError(msg)
