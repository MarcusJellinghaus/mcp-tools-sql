"""MCP tools for database schema exploration."""

from __future__ import annotations

import inspect
import re
import tomllib
from collections.abc import Callable
from fnmatch import fnmatch
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, Optional

from pydantic import Field

from mcp_tools_sql.config.models import QueryConfig
from mcp_tools_sql.formatting import format_rows
from mcp_tools_sql.utils.data_type_utility.type_mapping import resolve_python_type

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from mcp_tools_sql.backends.base import DatabaseBackend


def load_default_queries() -> dict[str, QueryConfig]:
    """Load built-in schema queries from default_queries.toml.

    Returns:
        Dict mapping query name to QueryConfig.
    """
    toml_path = Path(__file__).parent / "default_queries.toml"
    with open(toml_path, "rb") as f:
        data = tomllib.load(f)
    return {
        name: QueryConfig.model_validate(cfg) for name, cfg in data["queries"].items()
    }


def register_builtin_tools(
    mcp: FastMCP,
    backend: DatabaseBackend,
    backend_name: str,
) -> None:
    """Load default_queries.toml and register all schema tools on mcp."""
    queries = load_default_queries()
    for name, config in queries.items():
        fn = _build_tool_fn(name, config, backend, backend_name)
        mcp.add_tool(fn)


def _extract_sql_params(sql: str) -> set[str]:
    """Scan SQL for :param_name references, return set of param names."""
    return set(re.findall(r":(\w+)", sql))


def _apply_filter(
    rows: list[dict[str, Any]],
    filter_pattern: str | None,
) -> list[dict[str, Any]]:
    """Apply fnmatch glob filter on the 'name' column. Returns filtered rows."""
    if not filter_pattern:
        return rows
    return [
        r
        for r in rows
        if fnmatch(str(r.get("name", "")).lower(), filter_pattern.lower())
    ]


def _build_tool_fn(
    name: str,
    config: QueryConfig,
    backend: DatabaseBackend,
    backend_name: str,
) -> Callable[..., Any]:
    """Build a dynamic async function for one query config entry.

    Returns an async function with __signature__ set from config params,
    ready for mcp.add_tool().
    """
    resolved_sql = config.resolve_sql(backend_name)
    sql_params = _extract_sql_params(resolved_sql)

    async def _tool_fn(**kwargs: Any) -> str:
        max_rows: int = kwargs.pop("max_rows", config.max_rows)
        filter_pattern: str | None = kwargs.pop("filter", None)

        # Strip kwargs to only params referenced in resolved SQL
        stripped = {k: v for k, v in kwargs.items() if k in sql_params}
        rows = backend.execute_query(resolved_sql, stripped or None)
        rows = _apply_filter(rows, filter_pattern)
        return format_rows(rows, max_rows)

    # Build signature from config.params
    sig_params: list[inspect.Parameter] = []
    for param_cfg in config.params.values():
        python_type = resolve_python_type(param_cfg.type)
        desc = param_cfg.description

        if param_cfg.name == "max_rows":
            # max_rows uses config.max_rows as default
            annotation: Any = (
                Annotated[Optional[python_type], Field(description=desc)]  # noqa: UP007
                if desc
                else Optional[python_type]  # noqa: UP007
            )
            sig_params.append(
                inspect.Parameter(
                    param_cfg.name,
                    kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    default=config.max_rows,
                    annotation=annotation,
                )
            )
        elif param_cfg.required:
            annotation = (
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

    _tool_fn.__signature__ = inspect.Signature(sig_params)  # type: ignore[attr-defined]
    _tool_fn.__name__ = name
    _tool_fn.__doc__ = config.description
    return _tool_fn
