"""Config authoring helpers: builders for query and update configs."""

from __future__ import annotations

from typing import Any

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
