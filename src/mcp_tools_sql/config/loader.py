"""Configuration loading and resolution."""

from __future__ import annotations

import logging
import tomllib
from pathlib import Path

from mcp_tools_sql.config.models import ConnectionConfig, QueryFileConfig, UserConfig

_SENSITIVE_KEYS = {"password", "connection_string", "credential_env_var"}
_logger = logging.getLogger(__name__)


def _has_sensitive_keys(data: dict[str, object]) -> list[str]:
    """Recursively scan a parsed TOML dict for sensitive keys."""
    found: list[str] = []
    for key, value in data.items():
        if key in _SENSITIVE_KEYS:
            found.append(key)
        if isinstance(value, dict):
            found.extend(_has_sensitive_keys(value))
    return found


def _read_toml(path: Path) -> dict[str, object]:
    """Read and parse a TOML file, wrapping errors in ValueError."""
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
    """Load and validate the project query configuration file."""
    if not path.exists():
        msg = f"Cannot read {path}: file does not exist"
        raise ValueError(msg)

    data = _read_toml(path)

    sensitive = _has_sensitive_keys(data)
    if sensitive:
        keys_str = ", ".join(sorted(sensitive))
        _logger.warning(
            "Query config %s contains sensitive key(s): %s. "
            "Move credentials to user config (~/.mcp-tools-sql/config.toml).",
            path,
            keys_str,
        )

    return QueryFileConfig.model_validate(data)


def load_user_config(path: Path | None = None) -> UserConfig:
    """Load user config from path or default location.

    Returns defaults if the file does not exist. No side effects.
    """
    if path is None:
        path = Path.home() / ".mcp-tools-sql" / "config.toml"

    if not path.exists():
        return UserConfig()

    data = _read_toml(path)
    return UserConfig.model_validate(data)


def resolve_connection(
    query_config: QueryFileConfig,
    user_config: UserConfig,
) -> ConnectionConfig:
    """Merge project and user configs to produce a final ConnectionConfig."""
    # TODO: overlay user credentials onto project connection settings
    _ = query_config, user_config
    raise NotImplementedError
