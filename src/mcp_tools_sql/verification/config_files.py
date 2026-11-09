"""Config files section: query config + database config resolution and parse."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, NamedTuple

from pydantic import BaseModel, ValidationError

from mcp_tools_sql.config.loader import (
    _has_sensitive_keys,
    discover_query_config,
    load_database_config,
    read_query_config_data,
)
from mcp_tools_sql.config.models import (
    DatabaseConfig,
    QueryConfig,
    QueryFileConfig,
    UpdateConfig,
    count_rows_violation,
)
from mcp_tools_sql.utils.user_app_data import get_user_app_data_dir
from mcp_tools_sql.verification._helpers import (
    CheckResult,
    make_entry,
    make_warn_entry,
)

_ENTRY_KINDS = ("queries", "updates")


class LoadedConfigs(NamedTuple):
    """CONFIG rows plus the configs they were derived from.

    ``query_config`` is ``None`` when the top level failed to load and holds
    valid ``[queries.*]`` / ``[updates.*]`` entries only. ``db_config`` is
    ``None`` when the file is absent or failed to parse. ``allow_updates`` is
    ``None`` when the database config failed to parse, and the default when
    the file is absent.
    """

    checks: dict[str, CheckResult]
    query_config: QueryFileConfig | None
    db_config: DatabaseConfig | None
    allow_updates: bool | None


def _load_entries(
    data: dict[str, object],
    kind: str,
    model: type[BaseModel],
    checks: dict[str, CheckResult],
) -> dict[str, Any]:
    """Validate each ``[<kind>.*]`` entry on its own.

    Adds a ``<kind>.parse`` ERR row when the value is not a table, and a
    ``<kind>.<name>.parse`` ERR row per invalid entry.

    Returns:
        The valid entries, keyed by name, in file order.
    """
    raw = data.get(kind, {})
    if not isinstance(raw, dict):
        checks[f"{kind}.parse"] = make_entry(
            ok=False, error=f"`{kind}` must be a table"
        )
        return {}
    valid: dict[str, Any] = {}
    for name, entry in raw.items():
        try:
            valid[name] = model.model_validate(entry)
        except ValidationError as exc:
            checks[f"{kind}.{name}.parse"] = make_entry(ok=False, error=str(exc))
    return valid


def _load_query_half(
    config_path: Path | None,
    project_dir: Path,
    checks: dict[str, CheckResult],
) -> QueryFileConfig | None:
    """Discover, read and validate the query config, entry by entry.

    Validates through the models directly (not ``load_query_config``), so no
    sensitive-key warning is logged; the scan becomes a CONFIG row instead.

    Returns:
        The query config holding valid entries only, or ``None`` when the
        path, the file or its top level could not be loaded.
    """
    try:
        path = discover_query_config(config_path, project_dir=project_dir)
        checks["query_config_path"] = make_entry(ok=True, value=str(path))
    except ValueError as exc:
        checks["query_config_path"] = make_entry(ok=False, error=str(exc))
        checks["query_config_parse"] = make_entry(
            ok=False, error="skipped (path not resolved)"
        )
        return None

    try:
        data = read_query_config_data(path)
    except ValueError as exc:
        checks["query_config_parse"] = make_entry(ok=False, error=str(exc))
        return None

    query_config: QueryFileConfig | None = None
    try:
        top = QueryFileConfig.model_validate(
            {k: v for k, v in data.items() if k not in _ENTRY_KINDS}
        )
        checks["query_config_parse"] = make_entry(ok=True, value="loaded")
    except ValidationError as exc:
        checks["query_config_parse"] = make_entry(ok=False, error=str(exc))
    else:
        queries = _load_entries(data, "queries", QueryConfig, checks)
        updates = _load_entries(data, "updates", UpdateConfig, checks)
        query_config = top.model_copy(update={"queries": queries, "updates": updates})
        # Entries are validated separately, so re-run the cross-entry check.
        violation = count_rows_violation(top.limits, queries)
        if violation:
            checks["query_config_parse"] = make_entry(ok=False, error=violation)

    found = _has_sensitive_keys(data)
    if found:
        checks["query_config_sensitive_keys"] = make_warn_entry(
            ", ".join(sorted(set(found))),
            "Move credentials to ~/.mcp-tools-sql/config.toml",
        )
    return query_config


def verify_config_files(
    config_path: Path | None,
    db_config_path: Path | None,
    project_dir: Path,
) -> LoadedConfigs:
    """Load both config files once and verify they resolve and parse cleanly.

    The query config is discovered under ``project_dir`` unless
    ``config_path`` is given. Each ``[queries.*]`` / ``[updates.*]`` entry is
    validated on its own, so one bad entry does not hide the others.

    Returns:
        A :class:`LoadedConfigs` with the CONFIG rows (path and parse status of
        both files, per-entry parse errors, a ``query_config_sensitive_keys``
        warning when credentials are found in the query config, and the
        cross-file rows) and the loaded configs.
    """
    result: dict[str, CheckResult] = {}
    db_config: DatabaseConfig | None = None
    allow_updates: bool | None = DatabaseConfig().security.allow_updates

    query_config = _load_query_half(config_path, project_dir, result)

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
            allow_updates = db_config.security.allow_updates
            result["database_config_parse"] = make_entry(ok=True, value="loaded")
        except ValueError as exc:
            allow_updates = None
            result["database_config_parse"] = make_entry(ok=False, error=str(exc))

    # Cross-file static checks (rules 1/4/5/6). Rules 2/3/7 are enforced by the
    # model validators at load; a violation raises above and is reported via the
    # existing parse-error row, so this block is only reached when both configs
    # loaded and those rules already hold. Only valid entries are walked.
    if query_config is not None and db_config is not None:
        _append_cross_file_checks(result, query_config, db_config)

    return LoadedConfigs(result, query_config, db_config, allow_updates)


def _append_cross_file_checks(
    result: dict[str, CheckResult],
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
