"""Updates section: table exists, key column exists, fields exist."""

from __future__ import annotations

from typing import Any

from mcp_tools_sql.backends.base import DatabaseBackend
from mcp_tools_sql.backends.registry import BackendRegistry
from mcp_tools_sql.config.models import ResolvedTargets, UpdateConfig
from mcp_tools_sql.identifiers import IDENTIFIER_PATTERN, identifier_error
from mcp_tools_sql.verification._helpers import make_entry, make_skipped_entry


def _list_table_columns(
    backend: DatabaseBackend,
    backend_name: str,
    schema: str,
    table: str,
) -> list[str] | None:
    """Return column names for ``table`` in ``schema``, or ``None`` if missing.

    SQLite ignores ``schema`` (single-database file). MSSQL/PostgreSQL look up
    via ``INFORMATION_SCHEMA.COLUMNS`` filtered by both schema and table; the
    user must set ``schema`` in their config when the table lives outside the
    connection's default schema — verify never silently substitutes ``dbo`` or
    ``public``.
    """
    if backend_name == "sqlite":
        rows = backend.execute_query(
            "SELECT name FROM pragma_table_info(:table)",
            {"table": table},
        )
        cols = [r["name"] for r in rows]
        return cols if cols else None

    if backend_name in ("mssql", "postgresql"):
        rows = backend.execute_query(
            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA = :schema AND TABLE_NAME = :table",
            {"schema": schema, "table": table},
        )
        cols = [r["COLUMN_NAME"] for r in rows]
        return cols if cols else None

    return None


def verify_one_update(
    name: str,
    ucfg: UpdateConfig,
    targets: ResolvedTargets,
    registry: BackendRegistry,
    reachable: dict[tuple[str, str], bool],
) -> dict[str, Any]:
    """Per-entry validation for a single update against its own pinned target.

    The identifier checks run statically (independent of connectivity). When
    the update's resolved target is reachable, its columns are listed via the
    registry-owned backend; when unreachable, the three rows become skip rows
    naming the connection instead of being blanked. An unresolvable pin (bad
    connection/database) yields error rows.

    Returns:
        Dict containing 1 row on the bad-identifier branch (``<name>.table``)
        or 3 rows on the missing-table / skip / happy branches
        (``<name>.table``, ``<name>.key_column``, ``<name>.fields``).
        No ``overall_ok``.
    """
    result: dict[str, Any] = {}
    bad_idents: list[str] = []
    if not IDENTIFIER_PATTERN.match(ucfg.table):
        bad_idents.append(ucfg.table)
    if ucfg.schema_name and not IDENTIFIER_PATTERN.match(ucfg.schema_name):
        bad_idents.append(ucfg.schema_name)
    if bad_idents:
        result[f"{name}.table"] = make_entry(
            ok=False,
            value=ucfg.table,
            error=identifier_error(value=bad_idents[0], update_name=name),
        )
        # NOTE: Key insertion order is load-bearing — the CLI snapshot test and
        # verify_queries/verify_updates assert byte-equality against this order.
        # Do not refactor to dict comprehensions or dict() constructors.
        return result

    try:
        target = targets.resolve_pinned(ucfg.connection or None, ucfg.database or None)
    except ValueError as exc:
        result[f"{name}.table"] = make_entry(ok=False, value=ucfg.table, error=str(exc))
        result[f"{name}.key_column"] = make_entry(
            ok=False, value="(skipped)", error=str(exc)
        )
        result[f"{name}.fields"] = make_entry(
            ok=False, value="(skipped)", error=str(exc)
        )
        return result

    if not reachable.get((target.connection, target.database), False):
        result[f"{name}.table"] = make_skipped_entry(target.connection)
        result[f"{name}.key_column"] = make_skipped_entry(target.connection)
        result[f"{name}.fields"] = make_skipped_entry(target.connection)
        # NOTE: Key insertion order is load-bearing — the CLI snapshot test and
        # verify_queries/verify_updates assert byte-equality against this order.
        # Do not refactor to dict comprehensions or dict() constructors.
        return result

    backend = registry.backend_for(target)
    cols = _list_table_columns(
        backend, target.backend_name, ucfg.schema_name, ucfg.table
    )

    if cols is None:
        qualified = f"{ucfg.schema_name}.{ucfg.table}".lstrip(".")
        result[f"{name}.table"] = make_entry(
            ok=False, value=qualified, error="Table not found"
        )
        result[f"{name}.key_column"] = make_entry(
            ok=False, value="(skipped)", error="Table not found"
        )
        result[f"{name}.fields"] = make_entry(
            ok=False, value="(skipped)", error="Table not found"
        )
        # NOTE: Key insertion order is load-bearing — the CLI snapshot test and
        # verify_queries/verify_updates assert byte-equality against this order.
        # Do not refactor to dict comprehensions or dict() constructors.
        return result

    result[f"{name}.table"] = make_entry(ok=True, value=ucfg.table)

    key_field = ucfg.key.field if ucfg.key else ""
    if not key_field:
        result[f"{name}.key_column"] = make_entry(
            ok=False, value="(none)", error="No key configured"
        )
    elif not IDENTIFIER_PATTERN.match(key_field):
        result[f"{name}.key_column"] = make_entry(
            ok=False,
            value=key_field,
            error=identifier_error(value=key_field, update_name=name),
        )
    elif key_field not in cols:
        result[f"{name}.key_column"] = make_entry(
            ok=False,
            value=key_field,
            error=f"Column not found in {ucfg.table}",
        )
    else:
        result[f"{name}.key_column"] = make_entry(ok=True, value=key_field)

    fields_value = ", ".join(
        f"{f.field}(req)" if f.required else f.field for f in ucfg.fields
    )
    bad_fields = [f.field for f in ucfg.fields if not IDENTIFIER_PATTERN.match(f.field)]
    if bad_fields:
        result[f"{name}.fields"] = make_entry(
            ok=False,
            value=fields_value,
            error=identifier_error(value=bad_fields[0], update_name=name),
        )
    else:
        missing = [f.field for f in ucfg.fields if f.field not in cols]
        if missing:
            result[f"{name}.fields"] = make_entry(
                ok=False,
                value=fields_value,
                error=f"Missing columns: {', '.join(missing)}",
            )
        else:
            result[f"{name}.fields"] = make_entry(ok=True, value=fields_value)

    return result


def verify_updates(
    updates: dict[str, UpdateConfig],
    targets: ResolvedTargets,
    registry: BackendRegistry,
    reachable: dict[tuple[str, str], bool],
) -> dict[str, Any]:
    """Per-update validation: table exists, key column exists, fields exist.

    Each update is validated against its own resolved target; updates pinned to
    an unreachable connection report skip rows (naming the connection) instead
    of being blanked, while a reachable update in the same run still gets a real
    verdict.

    Returns:
        Standard verifier result dict with three rows per update
        (``<name>.table``, ``<name>.key_column``, ``<name>.fields``) and
        an ``overall_ok`` flag. When the table is missing, all three rows
        are emitted as ``[ERR]`` rather than skipped.
    """
    result: dict[str, Any] = {}
    for name, ucfg in updates.items():
        result.update(verify_one_update(name, ucfg, targets, registry, reachable))
    result["overall_ok"] = all(
        entry["ok"] or entry.get("warn", False)
        for key, entry in result.items()
        if key != "overall_ok"
    )
    return result
