"""Tests for the dynamic per-tool argument parser (`tool_args.py`)."""

from __future__ import annotations

import inspect
from typing import Annotated, Any, Literal, Optional

import pytest
from mcp.server.fastmcp.tools.base import Tool
from pydantic import Field

from mcp_tools_sql.cli.commands.tool_args import build_kwargs, build_tool_argparser
from mcp_tools_sql.tool_builder import _UNSET, build_tool_fn


async def _body(**kwargs: Any) -> str:
    return str(kwargs)


def _build_tool(sig_params: list[inspect.Parameter]) -> Tool:
    """Build a `Tool` from hand-built signature parameters."""
    fn = build_tool_fn("t", sig_params, _body, "Test tool.")
    return Tool.from_function(fn)


def test_required_str_param_is_required() -> None:
    """A required `str` param: omitting `--name` is `SystemExit(2)`."""
    tool = _build_tool(
        [
            inspect.Parameter(
                "name",
                kind=inspect.Parameter.KEYWORD_ONLY,
                annotation=Annotated[str, Field(description="Name")],
            )
        ]
    )
    parser = build_tool_argparser(tool, "t")

    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args([])
    assert exc_info.value.code == 2

    ns = parser.parse_args(["--name", "alice"])
    assert build_kwargs(ns) == {"name": "alice"}


def test_optional_int_param_omittable_and_parsed() -> None:
    """An optional `int` param: omitted is absent; `--count 5` parses as `int`."""
    tool = _build_tool(
        [
            inspect.Parameter(
                "count",
                kind=inspect.Parameter.KEYWORD_ONLY,
                default=1,
                annotation=Optional[int],  # noqa: UP007
            )
        ]
    )
    parser = build_tool_argparser(tool, "t")

    kwargs_omitted = build_kwargs(parser.parse_args([]))
    assert "count" not in kwargs_omitted

    kwargs_set = build_kwargs(parser.parse_args(["--count", "5"]))
    assert kwargs_set == {"count": 5}


def test_bool_param_flag_and_no_flag() -> None:
    """A `bool` param: `--flag`/`--no-flag` both work; omitted is absent."""
    tool = _build_tool(
        [
            inspect.Parameter(
                "flag",
                kind=inspect.Parameter.KEYWORD_ONLY,
                default=False,
                annotation=bool,
            )
        ]
    )
    parser = build_tool_argparser(tool, "t")

    assert build_kwargs(parser.parse_args([])) == {}
    assert build_kwargs(parser.parse_args(["--flag"])) == {"flag": True}
    assert build_kwargs(parser.parse_args(["--no-flag"])) == {"flag": False}


def test_literal_param_enforces_choices() -> None:
    """A `Literal["a", "b"]` param: `choices` enforced, bad value is `SystemExit(2)`."""
    tool = _build_tool(
        [
            inspect.Parameter(
                "mode",
                kind=inspect.Parameter.KEYWORD_ONLY,
                annotation=Literal["a", "b"],
            )
        ]
    )
    parser = build_tool_argparser(tool, "t")

    assert build_kwargs(parser.parse_args(["--mode", "a"])) == {"mode": "a"}
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["--mode", "c"])
    assert exc_info.value.code == 2


def test_params_dict_repeatable_flag() -> None:
    """A `params: dict[str, Any] | None` param: repeatable `--param KEY=VALUE`."""
    tool = _build_tool(
        [
            inspect.Parameter(
                "params",
                kind=inspect.Parameter.KEYWORD_ONLY,
                default=None,
                annotation=Optional[dict[str, Any]],  # noqa: UP007
            )
        ]
    )
    parser = build_tool_argparser(tool, "t")

    kwargs = build_kwargs(parser.parse_args(["--param", "id=5", "--param", "name=foo"]))
    assert kwargs == {"params": {"id": "5", "name": "foo"}}

    assert build_kwargs(parser.parse_args([])) == {}

    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["--param", "no-equals-sign"])
    assert exc_info.value.code == 2


def test_columns_list_repeatable_flag() -> None:
    """A `columns: list[str] | None` param: repeatable `--column NAME`."""
    tool = _build_tool(
        [
            inspect.Parameter(
                "columns",
                kind=inspect.Parameter.KEYWORD_ONLY,
                default=None,
                annotation=Optional[list[str]],  # noqa: UP007
            )
        ]
    )
    parser = build_tool_argparser(tool, "t")

    kwargs = build_kwargs(parser.parse_args(["--column", "id", "--column", "name"]))
    assert kwargs == {"columns": ["id", "name"]}
    assert build_kwargs(parser.parse_args([])) == {}


def test_unset_sentinel_default_is_treated_as_optional() -> None:
    """An `update_*`-shaped field defaulting to the real `_UNSET` sentinel is omittable."""
    tool = _build_tool(
        [
            inspect.Parameter(
                "notes",
                kind=inspect.Parameter.KEYWORD_ONLY,
                default=_UNSET,
                annotation=Annotated[
                    Optional[str], Field(description="Optional notes")  # noqa: UP007
                ],
            )
        ]
    )
    parser = build_tool_argparser(tool, "t")

    assert build_kwargs(parser.parse_args([])) == {}
    assert build_kwargs(parser.parse_args(["--notes", "hi"])) == {"notes": "hi"}
