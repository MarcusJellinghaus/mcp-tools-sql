"""`tool` subcommand — list and call MCP tools directly."""

from __future__ import annotations

import argparse
import asyncio
import sys

from mcp_tools_sql.cli.commands.tool_args import build_kwargs, build_tool_argparser
from mcp_tools_sql.cli.commands.tool_dispatch import invoke_tool
from mcp_tools_sql.cli.commands.tool_help import render_overview, render_tool_detail
from mcp_tools_sql.cli.parsers import HelpHintArgumentParser
from mcp_tools_sql.server import build_tool_server

_HELP_TOKENS = ("--help", "-h")


def add_subparser(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """Register the bare `tool` subparser (its own args are parsed by `run`)."""
    subparsers.add_parser(
        "tool",
        add_help=False,
        help="List and call MCP tools directly (bypasses the MCP client).",
    )


def _build_name_parser(tool_names: list[str]) -> argparse.ArgumentParser:
    """Build the inner parser that consumes the tool name and remainder.

    Returns:
        A parser with a ``name`` positional (restricted to ``tool_names``)
        and a ``rest`` positional capturing every remaining token.
    """
    parser = HelpHintArgumentParser(prog="mcp-tools-sql tool", add_help=False)
    parser.add_argument("name", nargs="?", default=None, choices=sorted(tool_names))
    parser.add_argument("rest", nargs=argparse.REMAINDER)
    return parser


def run(args: argparse.Namespace) -> int:
    """Entry point for the `tool` subcommand.

    Returns:
        Process exit code.

    Raises:
        RuntimeError: If the tool vanishes between listing and lookup
            (defensive guard, not expected in practice).
    """
    try:
        server, _qpath = build_tool_server(args)
    except (ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        print(
            "The tool list depends on the config. Run 'mcp-tools-sql help config' "
            "to set it up, then 'mcp-tools-sql verify'.",
            file=sys.stderr,
        )
        return 1
    try:
        server.register_all()
        tools = server.mcp._tool_manager.list_tools()  # noqa: SLF001
        tool_argv: list[str] = args.tool_argv
        if not tool_argv or tool_argv[0] in _HELP_TOKENS:
            print(render_overview(tools))
            return 0
        name_parser = _build_name_parser([t.name for t in tools])
        ns = name_parser.parse_args(tool_argv)
        tool = server.mcp._tool_manager.get_tool(ns.name)  # noqa: SLF001
        if tool is None:
            raise RuntimeError(f"tool {ns.name!r} vanished between listing and lookup")
        if ns.rest and ns.rest[0] in _HELP_TOKENS:
            print(render_tool_detail(tool))
            return 0
        parser = build_tool_argparser(tool, prog=f"mcp-tools-sql tool {ns.name}")
        tool_ns = parser.parse_args(ns.rest)
        kwargs = build_kwargs(tool_ns)
        exit_code, output = asyncio.run(invoke_tool(tool, kwargs))
        print(output)
        return exit_code
    finally:
        server.close()
