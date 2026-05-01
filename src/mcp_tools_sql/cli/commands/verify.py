"""verify subcommand."""

from __future__ import annotations

import argparse

from mcp_tools_sql.cli.parsers import WideHelpFormatter


def add_subparser(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """Register `verify` subparser (no subcommand-level flags; uses top-level)."""
    subparsers.add_parser(
        "verify",
        help=(
            "Validate environment, configuration, dependencies, and connectivity. "
            "Exit 0 on success, 1 on any error"
        ),
        formatter_class=WideHelpFormatter,
    )


def run(args: argparse.Namespace) -> int:
    """Entry point. Returns process exit code."""
    raise NotImplementedError("verify: implemented in steps 5-9")
