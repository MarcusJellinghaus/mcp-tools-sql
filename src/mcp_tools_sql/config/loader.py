"""Configuration loading and resolution."""

from __future__ import annotations

import logging
import os
import re
import tomllib
from pathlib import Path

from mcp_tools_sql.config.models import (
    DatabaseConfig,
    QueryFileConfig,
    ResolvedTarget,
    ResolvedTargets,
)
from mcp_tools_sql.utils.user_app_data import get_user_app_data_dir

_SENSITIVE_KEYS = {"password"}
_logger = logging.getLogger(__name__)
_VAR_RE = re.compile(r"\$\{([^}]+)\}")


def _expand_env_vars(data: object) -> object:
    """Recursively expand ``${NAME}`` references in string values via os.environ.

    Walks dicts and lists; leaves non-string scalars untouched. Raises
    ``ValueError`` when a referenced variable is not set.

    Returns:
        The same structure shape with strings rewritten.
    """
    if isinstance(data, dict):
        return {k: _expand_env_vars(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_expand_env_vars(v) for v in data]
    if isinstance(data, str):

        def _sub(match: re.Match[str]) -> str:
            name = match.group(1)
            if name not in os.environ:
                raise ValueError(
                    f"Unset environment variable '${{{name}}}' referenced in config"
                )
            return os.environ[name]

        return _VAR_RE.sub(_sub, data)
    return data


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
        path = get_user_app_data_dir("mcp-tools-sql") / "config.toml"

    if not path.exists():
        return DatabaseConfig()

    data = _read_toml(path)
    expanded = _expand_env_vars(data)
    return DatabaseConfig.model_validate(expanded)


def resolve_targets(
    query_config: QueryFileConfig,
    db_config: DatabaseConfig,
) -> ResolvedTargets:
    """Resolve every ``(connection, database)`` pair into ``ResolvedTargets``.

    Iterates connections in config order, and each connection's databases in
    config order, building one :class:`ResolvedTarget` per pair with its
    ``config.database`` pinned to that catalog. The default target is the file
    default connection's default database.

    Returns:
        The full set of resolved targets with the default marked.

    Raises:
        ValueError: If the file default connection name is missing or not found
            in db_config.connections.
    """
    file_conn = query_config.connection
    targets: list[ResolvedTarget] = []
    for cname, conn in db_config.connections.items():
        for db in conn.databases:
            is_default = cname == file_conn and db.name == conn.default_database
            targets.append(
                ResolvedTarget(
                    connection=cname,
                    database=db.name,
                    config=conn.model_copy(update={"database": db.name}),
                    backend_name=conn.backend,
                    is_default=is_default,
                    connection_description=conn.description,
                    database_description=db.description,
                )
            )

    default = next((t for t in targets if t.is_default), None)
    if default is None:
        if not file_conn:
            raise ValueError("No connection name specified in query config")
        available = list(db_config.connections.keys())
        raise ValueError(f"Connection '{file_conn}' not found. Available: {available}")

    return ResolvedTargets(
        targets=targets,
        default=default,
        file_default_connection=file_conn,
    )


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
