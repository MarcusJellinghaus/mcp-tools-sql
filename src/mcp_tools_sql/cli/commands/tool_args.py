"""Dynamic per-tool argument parser for the `tool` CLI subcommand."""

from __future__ import annotations

import argparse
import inspect
import types
from typing import TYPE_CHECKING, Annotated, Any, Literal, Union, get_args, get_origin

from pydantic.fields import FieldInfo

from mcp_tools_sql.cli.parsers import HelpHintArgumentParser

if TYPE_CHECKING:
    from mcp.server.fastmcp.tools.base import Tool


def _parse_kv(value: str) -> tuple[str, str]:
    """Split ``KEY=VALUE`` for ``--param``.

    Returns:
        The ``(key, value)`` pair.

    Raises:
        argparse.ArgumentTypeError: If ``value`` has no ``=``.
    """
    if "=" not in value:
        raise argparse.ArgumentTypeError(f"expected KEY=VALUE, got {value!r}")
    key, _, rest = value.partition("=")
    return key, rest


def _unwrap_annotation(annotation: Any) -> tuple[Any, str | None]:
    """Strip ``Annotated``/``Field`` metadata and ``Optional``/``X | None`` wrapping.

    Returns:
        The base type (or ``Literal[...]`` generic alias) and the `Field`
        description, if any.
    """
    description: str | None = None
    if get_origin(annotation) is Annotated:
        args = get_args(annotation)
        annotation = args[0]
        for meta in args[1:]:
            if isinstance(meta, FieldInfo) and meta.description:
                description = meta.description
    if get_origin(annotation) in (Union, types.UnionType):
        non_none = [arg for arg in get_args(annotation) if arg is not type(None)]
        if non_none:
            annotation = non_none[0]
    return annotation, description


def _add_argument(parser: argparse.ArgumentParser, param: inspect.Parameter) -> None:
    """Add one `--<name>` flag for ``param`` to ``parser``."""
    flag = f"--{param.name}"
    required = param.default is inspect.Parameter.empty
    base_type, description = _unwrap_annotation(param.annotation)

    if base_type is bool:
        parser.add_argument(
            flag,
            action=argparse.BooleanOptionalAction,
            default=argparse.SUPPRESS,
            required=required,
            help=description,
        )
        return

    if get_origin(base_type) is Literal:
        parser.add_argument(
            flag,
            type=str,
            choices=[str(choice) for choice in get_args(base_type)],
            default=argparse.SUPPRESS,
            required=required,
            help=description,
        )
        return

    scalar_type = int if base_type is int else float if base_type is float else str
    parser.add_argument(
        flag,
        type=scalar_type,
        default=argparse.SUPPRESS,
        required=required,
        help=description,
    )


def build_tool_argparser(tool: Tool, prog: str) -> argparse.ArgumentParser:
    """Build an `argparse.ArgumentParser` for one tool's call signature.

    Returns:
        A parser with one flag per parameter of ``tool.fn``'s signature.
    """
    parser = HelpHintArgumentParser(prog=prog)
    for param in inspect.signature(tool.fn).parameters.values():
        if param.name == "params":
            parser.add_argument(
                "--param",
                dest="params",
                action="append",
                type=_parse_kv,
                default=argparse.SUPPRESS,
                metavar="KEY=VALUE",
                help="Bind value for a :name placeholder (repeatable).",
            )
            continue
        if param.name == "columns":
            parser.add_argument(
                "--column",
                dest="columns",
                action="append",
                type=str,
                default=argparse.SUPPRESS,
                metavar="NAME",
                help="Column name (repeatable).",
            )
            continue
        _add_argument(parser, param)
    return parser


def build_kwargs(ns: argparse.Namespace) -> dict[str, Any]:
    """Turn a parsed `Namespace` back into a tool-call kwargs dict.

    Returns:
        A kwargs dict with ``params`` converted from
        ``list[tuple[str, str]]`` to ``dict[str, str]`` when present, and
        every other value passed through unchanged.
    """
    kwargs = dict(vars(ns))
    if "params" in kwargs:
        kwargs["params"] = dict(kwargs["params"])
    return kwargs
