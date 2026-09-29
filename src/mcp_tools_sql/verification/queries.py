"""Queries section: SQL EXPLAIN, params well-formed, row limits > 0."""

from __future__ import annotations

import datetime
from typing import Any, cast

from mcp_tools_sql.backends.base import DatabaseBackend, to_dialect
from mcp_tools_sql.backends.registry import BackendRegistry
from mcp_tools_sql.config.models import QueryConfig, QueryParamConfig, ResolvedTargets
from mcp_tools_sql.query_helpers import extract_sql_params, read_only_rejection
from mcp_tools_sql.verification._helpers import (
    make_entry,
    make_skipped_entry,
    make_skipped_not_read_only_entry,
    make_warn_entry,
)

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


def _positive_entry(field: str, value: int) -> dict[str, Any]:
    """Build a verifier entry asserting ``value > 0`` for ``field``.

    Returns:
        A standard verifier entry whose error names ``field`` when
        ``value`` is not positive.
    """
    ok = value > 0
    return make_entry(
        ok=ok,
        value=str(value),
        error="" if ok else f"{field} must be > 0",
    )


def _read_only_rows(
    name: str, qcfg: QueryConfig, pinned_backend: str
) -> dict[str, Any]:
    """Build one ``<name>.read_only[<backend>]`` row per declared variant.

    The variant set is the pinned backend plus every declared
    ``[queries.<name>.backends.*]`` key, pinned first and the rest in config
    order. Each variant's own SQL is resolved and put through
    :func:`read_only_rejection` — the same helper the startup gate uses, so the
    row predicts what the server will do. A backend name that maps to no
    sqlglot dialect is dead config: it warns rather than failing ``verify``
    over SQL that never executes.

    Returns:
        Dict of read-only rows keyed by ``<name>.read_only[<backend>]``.
    """
    variants = [pinned_backend] + [k for k in qcfg.backends if k != pinned_backend]
    rows: dict[str, Any] = {}
    for variant in variants:
        try:
            dialect = to_dialect(variant)
        except ValueError as exc:
            rows[f"{name}.read_only[{variant}]"] = make_warn_entry(
                "(unknown backend)", str(exc)
            )
            continue
        rejection = read_only_rejection(qcfg.resolve_sql(variant), dialect)
        rows[f"{name}.read_only[{variant}]"] = make_entry(
            ok=rejection is None,
            value="read-only" if rejection is None else "failed",
            error=rejection or "",
        )
    return rows


def verify_one_query(
    name: str,
    qcfg: QueryConfig,
    targets: ResolvedTargets,
    registry: BackendRegistry,
    reachable: dict[tuple[str, str], bool],
) -> dict[str, Any]:
    """Per-entry validation for a single query against its own pinned target.

    Resolves the query's pinned ``(connection, database)`` target and, when
    that target's connection is reachable, EXPLAINs the SQL against the
    registry-owned backend. When the target is unreachable the ``<name>.sql``
    row is a skip row naming the connection (the static ``params`` /
    ``max_rows_default`` / ``max_rows_hard`` checks always run). A query whose
    pinned variant is not provably read-only is never EXPLAINed at all: its
    ``<name>.sql`` row is a ``(skipped)`` warn row, and the ``read_only`` row
    carries the reason. An
    unresolvable pin (bad connection/database) yields error rows.

    Returns:
        Dict with keys ``<name>.sql``, one ``<name>.read_only[<backend>]`` row
        per declared backend variant, ``<name>.params``,
        ``<name>.max_rows_default`` and ``<name>.max_rows_hard``, in that
        order. An unresolvable pin yields a single un-suffixed
        ``<name>.read_only`` row instead, since no variant set can be formed
        without a target. No ``overall_ok``.
    """
    result: dict[str, Any] = {}
    try:
        target = targets.resolve_pinned(qcfg.connection or None, qcfg.database or None)
    except ValueError as exc:
        result[f"{name}.sql"] = make_entry(ok=False, value="failed", error=str(exc))
        result[f"{name}.read_only"] = make_entry(
            ok=False, value="(skipped)", error=str(exc)
        )
        result[f"{name}.params"] = make_entry(
            ok=False, value="(skipped)", error=str(exc)
        )
        result[f"{name}.max_rows_default"] = make_entry(
            ok=False, value="(skipped)", error=str(exc)
        )
        result[f"{name}.max_rows_hard"] = make_entry(
            ok=False, value="(skipped)", error=str(exc)
        )
        return result

    sql = qcfg.resolve_sql(target.backend_name)

    # The read-only verdict is computed first so a rejected query is never
    # EXPLAINed: the probe would send the operator SQL the gate refuses, and
    # the row would report the database's complaint instead of the real reason.
    read_only_rows = _read_only_rows(name, qcfg, target.backend_name)
    pinned_row = read_only_rows[f"{name}.read_only[{target.backend_name}]"]

    if not pinned_row["ok"]:
        result[f"{name}.sql"] = make_skipped_not_read_only_entry()
    elif reachable.get((target.connection, target.database), False):
        backend = registry.backend_for(target)
        ok, err = _check_sql_explain(sql, qcfg.params, target.backend_name, backend)
        result[f"{name}.sql"] = make_entry(
            ok=ok,
            value="EXPLAIN ok" if ok else "failed",
            error=err,
        )
    else:
        result[f"{name}.sql"] = make_skipped_entry(target.connection)

    result.update(read_only_rows)

    ok, err = _check_params_well_formed(sql, qcfg.params)
    result[f"{name}.params"] = make_entry(
        ok=ok,
        value="well-formed" if ok else "issue",
        error=err,
    )

    result[f"{name}.max_rows_default"] = _positive_entry(
        "max_rows_default", qcfg.max_rows_default
    )
    result[f"{name}.max_rows_hard"] = _positive_entry(
        "max_rows_hard", cast(int, qcfg.max_rows_hard)
    )
    return result


def verify_queries(
    queries: dict[str, QueryConfig],
    targets: ResolvedTargets,
    registry: BackendRegistry,
    reachable: dict[tuple[str, str], bool],
) -> dict[str, Any]:
    """Per-query validation: SQL EXPLAIN, params well-formed, row limits > 0.

    Each query is EXPLAINed against its own resolved target; queries pinned to
    an unreachable connection report a skip row (naming the connection) instead
    of being blanked, while a reachable query in the same run still gets a real
    verdict.

    Returns:
        Standard verifier result dict with the rows described by
        :func:`verify_one_query` for each query, plus an ``overall_ok`` flag.
    """
    result: dict[str, Any] = {}
    for name, qcfg in queries.items():
        result.update(verify_one_query(name, qcfg, targets, registry, reachable))
    result["overall_ok"] = all(
        entry["ok"] or entry.get("warn", False)
        for key, entry in result.items()
        if key != "overall_ok"
    )
    return result
