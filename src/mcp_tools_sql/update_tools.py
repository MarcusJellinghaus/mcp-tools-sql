"""MCP tools for executing pre-approved updates."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Annotated, Any, Optional

from pydantic import Field

from mcp_tools_sql.formatting import format_update_result
from mcp_tools_sql.identifiers import IDENTIFIER_PATTERN, identifier_error
from mcp_tools_sql.tool_builder import _UNSET, build_tool_fn
from mcp_tools_sql.tool_logging import log_tool_call
from mcp_tools_sql.utils.data_type_utility.type_mapping import resolve_python_type

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from mcp_tools_sql.backends.base import DatabaseBackend
    from mcp_tools_sql.config.models import UpdateConfig


def _validate_identifier(value: str, update_name: str) -> None:
    """Raise ``ValueError`` when ``value`` is not a valid SQL identifier.

    Raises:
        ValueError: If ``value`` does not match the identifier whitelist.
    """
    if not IDENTIFIER_PATTERN.match(value):
        raise ValueError(identifier_error(value, update_name))


def _build_update_sig_params(config: UpdateConfig) -> list[inspect.Parameter]:
    """Build the public signature parameters for an update tool.

    The key parameter is ``POSITIONAL_OR_KEYWORD`` and required; every
    field parameter is ``KEYWORD_ONLY`` so required/optional fields can
    interleave freely without the "non-default argument follows default
    argument" restriction.

    Returns:
        The ordered list of ``inspect.Parameter`` objects describing the
        tool's public signature.
    """
    assert config.key is not None
    sig_params: list[inspect.Parameter] = []

    key_type = resolve_python_type(config.key.type)
    key_annotation: Any = Annotated[key_type, Field(description=config.key.description)]
    sig_params.append(
        inspect.Parameter(
            config.key.field,
            kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
            annotation=key_annotation,
        )
    )

    for field_cfg in config.fields:
        python_type = resolve_python_type(field_cfg.type)
        if field_cfg.required:
            sig_params.append(
                inspect.Parameter(
                    field_cfg.field,
                    kind=inspect.Parameter.KEYWORD_ONLY,
                    annotation=Annotated[
                        python_type, Field(description=field_cfg.description)
                    ],
                )
            )
        else:
            sig_params.append(
                inspect.Parameter(
                    field_cfg.field,
                    kind=inspect.Parameter.KEYWORD_ONLY,
                    default=_UNSET,
                    annotation=Annotated[
                        Optional[python_type],  # noqa: UP007
                        Field(description=field_cfg.description),
                    ],
                )
            )

    return sig_params


def _build_update_body(
    name: str,
    config: UpdateConfig,
    qualified: str,
    backend: DatabaseBackend,
) -> Callable[..., Awaitable[str]]:
    """Build the async body closure that runs the UPDATE at call time.

    Returns:
        An async callable that executes the UPDATE and returns the
        formatted result string.
    """
    assert config.key is not None
    key_field = config.key.field
    field_names = [f.field for f in config.fields]

    async def body(**kwargs: Any) -> str:
        key_value = kwargs[key_field]
        field_values = {
            f: kwargs[f] for f in field_names if kwargs.get(f, _UNSET) is not _UNSET
        }
        if not field_values:
            raise ValueError(f"update {name!r}: at least one field value required")
        set_clause = ", ".join(f"{col}=:{col}" for col in field_values)
        sql = f"UPDATE {qualified} SET {set_clause} " f"WHERE {key_field}=:{key_field}"
        params = {**field_values, key_field: key_value}
        async with log_tool_call(name, params, sql=sql) as rec:
            affected = backend.execute_update(sql, params)
            rec.record(rows=affected, cols=len(field_values))
            return format_update_result(affected, qualified, key_field, key_value)

    return body


class UpdateTools:
    """Registers configured update tools on an MCP server."""

    def __init__(
        self,
        backend: DatabaseBackend,
        updates: dict[str, UpdateConfig],
        backend_name: str,
    ) -> None:
        self._backend = backend
        self._updates = updates
        self._backend_name = backend_name

    def register(self, mcp: FastMCP) -> None:
        """Register one MCP tool per configured update as ``update_<name>``.

        Raises:
            ValueError: If a tool name, table, schema, key field, or field
                fails the identifier whitelist, if ``key`` is missing, or if
                any field reuses the key column name.
        """
        for name, cfg in self._updates.items():
            if not IDENTIFIER_PATTERN.match(name):
                raise ValueError(
                    f"Invalid update tool name {name!r}: must match "
                    f"{IDENTIFIER_PATTERN.pattern}"
                )
            if cfg.key is None:
                raise ValueError(f"update {name!r} requires a key field")

            _validate_identifier(cfg.table, name)
            if cfg.schema_name:
                _validate_identifier(cfg.schema_name, name)
            _validate_identifier(cfg.key.field, name)
            for field_cfg in cfg.fields:
                _validate_identifier(field_cfg.field, name)

            for field_cfg in cfg.fields:
                if field_cfg.field == cfg.key.field:
                    raise ValueError(
                        f"update {name!r}: field {field_cfg.field!r} "
                        f"conflicts with key column {cfg.key.field!r}"
                    )

            qualified = (
                f"{cfg.schema_name}.{cfg.table}" if cfg.schema_name else cfg.table
            )
            sig_params = _build_update_sig_params(cfg)
            body = _build_update_body(name, cfg, qualified, self._backend)
            fn = build_tool_fn(name, sig_params, body, cfg.description)
            mcp.add_tool(
                fn,
                name=f"update_{name}",
                description=cfg.description,
            )
