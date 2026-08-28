"""Config files section: query config + database config resolution and parse."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from mcp_tools_sql.config.loader import (
    _has_sensitive_keys,
    _read_toml,
    discover_query_config,
    load_database_config,
    load_query_config,
)
from mcp_tools_sql.config.models import DatabaseConfig, QueryFileConfig
from mcp_tools_sql.utils.user_app_data import get_user_app_data_dir
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
    query_config: QueryFileConfig | None = None
    db_config: DatabaseConfig | None = None

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
            query_config = load_query_config(resolved_query)
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

    db_path = db_config_path or (get_user_app_data_dir("mcp-tools-sql") / "config.toml")
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
            db_config = load_database_config(db_path)
            result["database_config_parse"] = make_entry(ok=True, value="loaded")
        except ValueError as exc:
            result["database_config_parse"] = make_entry(ok=False, error=str(exc))

    # Cross-file static checks (rules 1/4/5/6). Rules 2/3/7 are enforced by the
    # model validators at load; a violation raises above and is reported via the
    # existing parse-error row, so this block is only reached when both configs
    # loaded cleanly and those rules already hold.
    if query_config is not None and db_config is not None:
        _append_cross_file_checks(result, query_config, db_config)

    result["overall_ok"] = all(
        entry["ok"] or entry.get("warn", False)
        for key, entry in result.items()
        if key != "overall_ok"
    )
    return result


def _append_cross_file_checks(
    result: dict[str, Any],
    query_config: QueryFileConfig,
    db_config: DatabaseConfig,
) -> None:
    """Append the cross-file static rows (rules 1/4/5/6) the model cannot see.

    These compare the query config against the database config: the file's
    ``connection`` (rule 1) and each ``[queries.*]`` / ``[updates.*]`` pinned
    ``connection`` (rule 4) and ``database`` (rules 5/6). Membership rules that a
    single model can enforce (2/3/7) are already guaranteed by load. No database
    access. Insertion order is stable (the verify snapshot asserts byte-equality).
    """
    connections = db_config.connections
    file_conn = query_config.connection

    # rule 1: the file-level `connection` names a real connection.
    if file_conn in connections:
        result["connection_valid"] = make_entry(ok=True, value=file_conn)
    else:
        result["connection_valid"] = make_entry(
            ok=False,
            value=file_conn,
            error=f"connection not found in database config; "
            f"available: {list(connections)}",
        )

    # rules 4/5/6: pinned connection/database on each query and update.
    scopes: list[tuple[str, Mapping[str, Any]]] = [
        ("queries", query_config.queries),
        ("updates", query_config.updates),
    ]
    for scope, items in scopes:
        for name, cfg in items.items():
            if cfg.connection:  # rule 4 (and rule 6's connection half)
                ok = cfg.connection in connections
                result[f"{scope}.{name}.connection"] = make_entry(
                    ok=ok,
                    value=cfg.connection,
                    error=(
                        ""
                        if ok
                        else f"connection not found; available: {list(connections)}"
                    ),
                )
            if cfg.database:  # rules 5/6
                resolved = cfg.connection or file_conn
                conn = connections.get(resolved)
                db_names = [d.name for d in conn.databases] if conn else []
                ok = cfg.database in db_names
                result[f"{scope}.{name}.database"] = make_entry(
                    ok=ok,
                    value=cfg.database,
                    error=(
                        ""
                        if ok
                        else f"database not in connection '{resolved}'; "
                        f"available: {db_names}"
                    ),
                )
