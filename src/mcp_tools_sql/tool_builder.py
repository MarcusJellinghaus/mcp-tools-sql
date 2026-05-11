"""Shared helpers for dynamic MCP tool registration."""

from __future__ import annotations

import inspect
import re
from collections.abc import Callable
from fnmatch import fnmatch
from typing import TYPE_CHECKING, Annotated, Any, Optional, cast

from pydantic import Field

from mcp_tools_sql.config.models import QueryConfig
from mcp_tools_sql.formatting import format_rows
from mcp_tools_sql.tool_logging import log_tool_call
from mcp_tools_sql.utils.data_type_utility.type_mapping import resolve_python_type

if TYPE_CHECKING:
    from mcp_tools_sql.backends.base import DatabaseBackend


def extract_sql_params(sql: str) -> set[str]:
    """Scan SQL for :param_name references.

    Returns:
        Set of parameter names found in the SQL string.
    """
    return set(re.findall(r":(\w+)", sql))


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


def build_tool_fn(
    name: str,
    config: QueryConfig,
    backend: DatabaseBackend,
    backend_name: str,
) -> Callable[..., Any]:
    """Build a dynamic async function for one query config entry.

    Returns:
        Async function with ``__signature__`` set from config params,
            ready for ``mcp.add_tool()``. The signature always includes an
            implicit ``max_rows`` parameter and, when
            ``config.filter_column`` is non-empty, a
            ``<filter_column>_filter`` parameter.
    """
    resolved_sql = config.resolve_sql(backend_name)
    sql_params = extract_sql_params(resolved_sql)
    filter_kwarg = f"{config.filter_column}_filter" if config.filter_column else None

    async def _tool_fn(**kwargs: Any) -> str:
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

        # Strip kwargs to only params referenced in resolved SQL
        stripped = {k: v for k, v in kwargs.items() if k in sql_params}

        async with log_tool_call(name, stripped, sql=resolved_sql) as rec:
            rows = backend.execute_query(resolved_sql, stripped or None)
            if filter_kwarg:
                rows = apply_filter(rows, config.filter_column, filter_pattern)
            rec.record(rows=len(rows), cols=len(rows[0]) if rows else 0)
            return format_rows(rows, requested) + note

    # Build signature from user-declared config.params only
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

    # Implicit max_rows parameter
    max_rows_desc = "Maximum rows to return"
    sig_params.append(
        inspect.Parameter(
            "max_rows",
            kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
            default=config.max_rows_default,
            annotation=Annotated[
                Optional[int], Field(description=max_rows_desc)
            ],  # noqa: UP007
        )
    )

    # Implicit <filter_column>_filter parameter when configured
    if filter_kwarg:
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

    _tool_fn.__signature__ = inspect.Signature(sig_params)  # type: ignore[attr-defined]
    _tool_fn.__name__ = name
    _tool_fn.__doc__ = config.description
    return _tool_fn
