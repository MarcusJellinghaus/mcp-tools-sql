"""Config files section: query config + database config resolution and parse."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp_tools_sql.config.loader import (
    _has_sensitive_keys,
    _read_toml,
    discover_query_config,
    load_database_config,
    load_query_config,
)
from mcp_tools_sql.verification._helpers import make_entry


def verify_config_files(
    config_path: Path | None,
    db_config_path: Path | None,
) -> dict[str, Any]:
    """Verify that both config files resolve to a path and parse cleanly.

    Returns:
        Standard verifier result dict with entries for the resolved path
        and parse status of the query config and the database config.
        A ``query_config_sensitive_keys`` entry is added with ``warn=True``
        when sensitive keys are detected in the query config.
    """
    result: dict[str, Any] = {}

    resolved_query: Path | None
    try:
        resolved_query = discover_query_config(config_path, project_dir=Path.cwd())
        result["query_config_path"] = make_entry(ok=True, value=str(resolved_query))
    except ValueError as exc:
        resolved_query = None
        result["query_config_path"] = make_entry(ok=False, error=str(exc))
        result["query_config_parse"] = make_entry(
            ok=False, error="skipped (path not resolved)"
        )

    if resolved_query is not None:
        try:
            load_query_config(resolved_query)
            result["query_config_parse"] = make_entry(ok=True, value="loaded")
        except ValueError as exc:
            result["query_config_parse"] = make_entry(ok=False, error=str(exc))

        try:
            data = _read_toml(resolved_query)
            found = _has_sensitive_keys(data)
        except ValueError:
            found = []
        if found:
            entry = make_entry(
                ok=False,
                value=", ".join(sorted(set(found))),
                error="Move credentials to ~/.mcp-tools-sql/config.toml",
            )
            entry["warn"] = True
            result["query_config_sensitive_keys"] = entry

    db_path = db_config_path or Path.home() / ".mcp-tools-sql" / "config.toml"
    if not db_path.exists():
        result["database_config_path"] = make_entry(
            ok=False,
            value=str(db_path),
            error="file not found",
            install_hint="run `mcp-tools-sql init --backend <backend>`",
        )
        result["database_config_parse"] = make_entry(
            ok=False, error="skipped (file not found)"
        )
    else:
        result["database_config_path"] = make_entry(ok=True, value=str(db_path))
        try:
            load_database_config(db_path)
            result["database_config_parse"] = make_entry(ok=True, value="loaded")
        except ValueError as exc:
            result["database_config_parse"] = make_entry(ok=False, error=str(exc))

    result["overall_ok"] = all(
        entry["ok"] or entry.get("warn", False)
        for key, entry in result.items()
        if key != "overall_ok"
    )
    return result
