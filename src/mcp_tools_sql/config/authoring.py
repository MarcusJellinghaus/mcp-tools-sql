"""Config authoring helpers: builders, storage, and listing for tool configs."""

from __future__ import annotations

from typing import Any

import tomlkit
import tomlkit.items

from mcp_tools_sql.config.models import (
    QueryConfig,
    QueryParamConfig,
    UpdateConfig,
    UpdateFieldConfig,
    UpdateKeyConfig,
)


def build_query_config(
    name: str,
    *,
    description: str = "",
    sql: str,
    params: dict[str, dict[str, Any]] | None = None,
    max_rows_default: int = 100,
    max_rows_hard: int | None = None,
    filter_column: str = "",
) -> QueryConfig:
    """Build a validated QueryConfig with ergonomic kwargs.

    Returns:
        A validated QueryConfig instance.
    """
    del name  # name is the TOML section key, handled by storage helpers
    params_in = params or {}
    typed_params = {
        key: QueryParamConfig(**{**inner, "name": key})
        for key, inner in params_in.items()
    }
    return QueryConfig(
        description=description,
        sql=sql,
        params=typed_params,
        max_rows_default=max_rows_default,
        max_rows_hard=max_rows_hard,
        filter_column=filter_column,
    )


def build_update_config(
    name: str,
    *,
    description: str = "",
    schema: str = "",
    table: str,
    key: dict[str, Any],
    fields: list[dict[str, Any]],
) -> UpdateConfig:
    """Build a validated UpdateConfig with ergonomic kwargs.

    Returns:
        A validated UpdateConfig instance.
    """
    del name  # name is the TOML section key, handled by storage helpers
    typed_key = UpdateKeyConfig(**key)
    typed_fields = [UpdateFieldConfig(**f) for f in fields]
    return UpdateConfig.model_validate(
        {
            "description": description,
            "schema": schema,
            "table": table,
            "key": typed_key,
            "fields": typed_fields,
        }
    )


def _to_toml_table(d: dict[str, Any]) -> tomlkit.items.Table:
    t = tomlkit.table()
    for k, v in d.items():
        t[k] = _to_toml_table(v) if isinstance(v, dict) else v
    return t


def _add_entry(
    doc: tomlkit.TOMLDocument,
    parent_key: str,
    name: str,
    payload: dict[str, Any],
) -> None:
    parent = doc.get(parent_key)
    if parent is None:
        parent = tomlkit.table()
        doc[parent_key] = parent
    if name in parent:
        raise ValueError(f"{parent_key}.{name} already exists")

    entry = tomlkit.table()

    for k, v in payload.items():
        if isinstance(v, (dict, list)):
            continue
        entry[k] = v

    for k, v in payload.items():
        if not isinstance(v, dict):
            continue
        sub = tomlkit.table()
        for ik, iv in v.items():
            sub[ik] = _to_toml_table(iv) if isinstance(iv, dict) else iv
        entry[k] = sub

    for k, v in payload.items():
        if not isinstance(v, list):
            continue
        aot = tomlkit.aot()
        for item in v:
            sub = tomlkit.table()
            for ik, iv in item.items():
                sub[ik] = iv
            aot.append(sub)
        entry[k] = aot

    parent[name] = entry


def _remove_entry(
    doc: tomlkit.TOMLDocument,
    parent_key: str,
    name: str,
) -> None:
    parent = doc.get(parent_key)
    if parent is None or name not in parent:
        raise KeyError(f"{parent_key}.{name}")
    del parent[name]
    if len(parent) == 0:
        del doc[parent_key]


def add_query(
    doc: tomlkit.TOMLDocument,
    name: str,
    qcfg: QueryConfig,
    *,
    include_defaults: bool = False,
) -> None:
    """Add a query entry to the document; ValueError on duplicate name."""
    payload = qcfg.model_dump(by_alias=True, exclude_defaults=not include_defaults)
    if not include_defaults and payload.get("max_rows_hard") == qcfg.max_rows_default:
        payload.pop("max_rows_hard", None)
    _add_entry(doc, "queries", name, payload)


def add_update(
    doc: tomlkit.TOMLDocument,
    name: str,
    ucfg: UpdateConfig,
    *,
    include_defaults: bool = False,
) -> None:
    """Add an update entry to the document; ValueError on duplicate name."""
    payload = ucfg.model_dump(by_alias=True, exclude_defaults=not include_defaults)
    _add_entry(doc, "updates", name, payload)


def remove_query(doc: tomlkit.TOMLDocument, name: str) -> None:
    """Remove a query entry; KeyError if the name or [queries] is absent."""
    _remove_entry(doc, "queries", name)


def remove_update(doc: tomlkit.TOMLDocument, name: str) -> None:
    """Remove an update entry; KeyError if the name or [updates] is absent."""
    _remove_entry(doc, "updates", name)


def list_configured_tools(
    doc: tomlkit.TOMLDocument,
) -> dict[str, list[str]]:
    """Return query and update names from the document.

    Missing sections become empty lists.
    """
    queries = doc.get("queries") or {}
    updates = doc.get("updates") or {}
    return {
        "queries": list(queries.keys()),
        "updates": list(updates.keys()),
    }
