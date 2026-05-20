"""Queries section: SQL EXPLAIN, params well-formed, max_rows_default > 0."""

from __future__ import annotations

import datetime
from typing import Any

from mcp_tools_sql.backends.base import DatabaseBackend
from mcp_tools_sql.config.models import QueryConfig, QueryParamConfig
from mcp_tools_sql.query_helpers import extract_sql_params
from mcp_tools_sql.verification._helpers import make_entry

_VALID_PARAM_TYPES = {"str", "int", "float", "datetime"}
_DUMMY_BY_TYPE: dict[str, Any] = {
    "str": "",
    "int": 0,
    "float": 0.0,
    "datetime": datetime.datetime(2000, 1, 1),
}


def _check_sql_explain(
    sql: str,
    params: dict[str, QueryParamConfig],
    backend_name: str,
    backend: DatabaseBackend,
) -> tuple[bool, str]:
    """Return ``(ok, error_message)`` for a single query's SQL.

    For SQLite, builds a dummy params dict (keys from ``params``, values
    placeholders chosen per declared type: ``""`` / ``0`` / ``0.0`` /
    ``datetime(2000, 1, 1)``) and passes it to
    ``backend.explain(sql, dummy_params)`` so ``EXPLAIN QUERY PLAN`` can
    compile the parameterized SQL. For MSSQL, also passes ``dummy`` params;
    ``backend.explain`` translates them and wraps the query in
    ``SET SHOWPLAN_TEXT ON/OFF``.
    """
    del backend_name  # Currently no per-backend branching is required.
    try:
        dummy = {name: _DUMMY_BY_TYPE.get(p.type, "") for name, p in params.items()}
        backend.explain(sql, dummy)
        return True, ""
    except Exception as exc:  # pylint: disable=broad-except
        return False, str(exc)


def _check_params_well_formed(
    sql: str, params: dict[str, QueryParamConfig]
) -> tuple[bool, str]:
    """Verify ``:name`` placeholders in SQL match config params + types.

    Returns:
        Tuple ``(ok, message)`` where ``ok`` is ``True`` when placeholders
        and config params line up with valid types, and ``message`` is a
        ``"; "``-joined description of any problems (empty when ``ok``).
    """
    sql_names = extract_sql_params(sql)
    config_names = set(params.keys())

    missing_in_config = sql_names - config_names
    extra_in_config = config_names - sql_names
    bad_types = [
        (n, p.type) for n, p in params.items() if p.type not in _VALID_PARAM_TYPES
    ]

    errors: list[str] = []
    if missing_in_config:
        errors.append(
            f"SQL :{','.join(sorted(missing_in_config))} not in config params"
        )
    if extra_in_config:
        errors.append(f"Config params {sorted(extra_in_config)} not used in SQL")
    if bad_types:
        errors.append("Invalid types: " + ", ".join(f"{n}={t!r}" for n, t in bad_types))
    return (not errors, "; ".join(errors))


def verify_one_query(
    name: str,
    qcfg: QueryConfig,
    backend_name: str,
    backend: DatabaseBackend,
) -> dict[str, Any]:
    """Per-entry validation for a single query.

    Returns:
        Three-row dict with keys ``<name>.sql``, ``<name>.params``,
        ``<name>.max_rows_default`` in that order. No ``overall_ok``.
    """
    result: dict[str, Any] = {}
    sql = qcfg.resolve_sql(backend_name)

    ok, err = _check_sql_explain(sql, qcfg.params, backend_name, backend)
    result[f"{name}.sql"] = make_entry(
        ok=ok,
        value="EXPLAIN ok" if ok else "failed",
        error=err,
    )

    ok, err = _check_params_well_formed(sql, qcfg.params)
    result[f"{name}.params"] = make_entry(
        ok=ok,
        value="well-formed" if ok else "issue",
        error=err,
    )

    ok = qcfg.max_rows_default > 0
    result[f"{name}.max_rows_default"] = make_entry(
        ok=ok,
        value=str(qcfg.max_rows_default),
        error="" if ok else "max_rows_default must be > 0",
    )
    return result


def verify_queries(
    queries: dict[str, QueryConfig],
    backend_name: str,
    backend: DatabaseBackend,
) -> dict[str, Any]:
    """Per-query validation: SQL EXPLAIN, params well-formed, max_rows_default > 0.

    Returns:
        Standard verifier result dict with three rows per query
        (``<name>.sql``, ``<name>.params``, ``<name>.max_rows_default``) and an
        ``overall_ok`` flag.
    """
    result: dict[str, Any] = {}
    for name, qcfg in queries.items():
        result.update(verify_one_query(name, qcfg, backend_name, backend))
    result["overall_ok"] = all(
        entry["ok"] for key, entry in result.items() if key != "overall_ok"
    )
    return result
