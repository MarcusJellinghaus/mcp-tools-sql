"""`tool` subcommand — list and call MCP tools directly."""

from __future__ import annotations

import argparse
import sys

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
    """
    try:
        server, _qpath = build_tool_server(args)
    except (ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
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
        if ns.rest and ns.rest[0] in _HELP_TOKENS:
            assert tool is not None
            print(render_tool_detail(tool))
            return 0
        raise NotImplementedError("tool invocation is wired in step 5")
    finally:
        server.close()
