"""init subcommand."""

from __future__ import annotations

import argparse
from pathlib import Path

from mcp_tools_sql.cli.parsers import WideHelpFormatter


def add_subparser(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """Register `init` subparser and its flags."""
    p = subparsers.add_parser(
        "init",
        help=(
            "Create starter mcp-tools-sql.toml and ~/.mcp-tools-sql/config.toml "
            "for a chosen backend"
        ),
        formatter_class=WideHelpFormatter,
    )
    p.add_argument(
        "--backend",
        choices=["sqlite", "mssql", "postgresql"],
        required=True,
        help="Database backend to scaffold for (sqlite, mssql, postgresql)",
    )
    p.add_argument(
        "--output",
        type=Path,
        default=Path("mcp-tools-sql.toml"),
        help="Path to write the project query config (default: ./mcp-tools-sql.toml)",
    )
    p.add_argument(
        "--pyproject",
        action="store_true",
        help=(
            "Append [tool.mcp-tools-sql] to existing pyproject.toml instead of "
            "writing a standalone file"
        ),
    )


def run(args: argparse.Namespace) -> int:
    """Entry point. Returns process exit code."""
    raise NotImplementedError("init: implemented in step 4")
