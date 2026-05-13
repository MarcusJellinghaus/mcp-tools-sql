"""Shared helpers for assembling query-style MCP tool signatures and bodies.

These building blocks are used by both ``query_tools`` (user-configured
queries) and ``schema_tools`` (built-in schema queries). They live one
layer below the tool modules so the two can share code without forming
a sibling-to-sibling dependency.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from fnmatch import fnmatch
from typing import TYPE_CHECKING, Annotated, Any, Optional, cast

from pydantic import Field

from mcp_tools_sql.formatting import format_rows
from mcp_tools_sql.tool_logging import log_tool_call
from mcp_tools_sql.utils.data_type_utility.type_mapping import resolve_python_type
from mcp_tools_sql.utils.sql_placeholders import extract_param_names

if TYPE_CHECKING:
    from mcp_tools_sql.backends.base import DatabaseBackend
    from mcp_tools_sql.config.models import QueryConfig


def extract_sql_params(sql: str) -> set[str]:
    """Scan SQL for :param_name references.

    Placeholders inside quoted strings and comments are ignored.

    Returns:
        Set of parameter names found in the SQL string.
    """
    return extract_param_names(sql)


def apply_filter(
    rows: list[dict[str, Any]],
    column: str,
    pattern: str | None,
) -> list[dict[str, Any]]:
    """Apply fnmatch glob filter on ``column``.

    Returns:
        Filtered rows matching the glob pattern.
    """
    if not pattern:
        return rows
    return [r for r in rows if fnmatch(str(r.get(column, "")).lower(), pattern.lower())]


def build_query_sig_params(config: QueryConfig) -> list[inspect.Parameter]:
    """Build the public signature parameters for a query tool.

    Returns:
        User-declared params followed by an implicit ``max_rows`` parameter
        and, when ``config.filter_column`` is non-empty, a
        ``<filter_column>_filter`` parameter.
    """
    sig_params: list[inspect.Parameter] = []
    for param_cfg in config.params.values():
        python_type = resolve_python_type(param_cfg.type)
        desc = param_cfg.description

        if param_cfg.required:
            annotation: Any = (
                Annotated[python_type, Field(description=desc)] if desc else python_type
            )
            sig_params.append(
                inspect.Parameter(
                    param_cfg.name,
                    kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    default=inspect.Parameter.empty,
                    annotation=annotation,
                )
            )
        else:
            annotation = (
                Annotated[Optional[python_type], Field(description=desc)]  # noqa: UP007
                if desc
                else Optional[python_type]  # noqa: UP007
            )
            sig_params.append(
                inspect.Parameter(
                    param_cfg.name,
                    kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    default=None,
                    annotation=annotation,
                )
            )

    max_rows_desc = "Maximum rows to return"
    sig_params.append(
        inspect.Parameter(
            "max_rows",
            kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
            default=config.max_rows_default,
            annotation=Annotated[int, Field(description=max_rows_desc)],
        )
    )

    if config.filter_column:
        filter_kwarg = f"{config.filter_column}_filter"
        filter_desc = (
            f"Glob pattern (case-insensitive) on the {config.filter_column} column"
        )
        sig_params.append(
            inspect.Parameter(
                filter_kwarg,
                kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
                default=None,
                annotation=Annotated[
                    Optional[str], Field(description=filter_desc)
                ],  # noqa: UP007
            )
        )

    return sig_params


def build_query_body(
    name: str,
    config: QueryConfig,
    backend: DatabaseBackend,
    backend_name: str,
    truncation_hint: str,
) -> Callable[..., Awaitable[str]]:
    """Build the async body closure that executes a query at tool call time.

    Returns:
        An async callable accepting the same kwargs as the tool's public
        signature, returning the formatted result text.
    """
    resolved_sql = config.resolve_sql(backend_name)
    sql_params = extract_sql_params(resolved_sql)
    filter_kwarg = f"{config.filter_column}_filter" if config.filter_column else None

    async def body(**kwargs: Any) -> str:
        requested: int = kwargs.pop("max_rows", config.max_rows_default)
        hard: int = cast(int, config.max_rows_hard)
        note = ""
        if requested > hard:
            note = (
                f"\n\nRequested max_rows={requested} exceeds hard limit "
                f"{hard}; capped at {hard}."
            )
            requested = hard
        filter_pattern: str | None = (
            kwargs.pop(filter_kwarg, None) if filter_kwarg else None
        )

        stripped = {k: v for k, v in kwargs.items() if k in sql_params}

        async with log_tool_call(name, stripped, sql=resolved_sql) as rec:
            rows = backend.execute_query(resolved_sql, stripped or None)
            if filter_kwarg:
                rows = apply_filter(rows, config.filter_column, filter_pattern)
            rec.record(rows=len(rows), cols=len(rows[0]) if rows else 0)
            return format_rows(rows, requested, truncation_hint=truncation_hint) + note

    return body
