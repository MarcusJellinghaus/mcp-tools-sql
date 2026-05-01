"""init subcommand."""

from __future__ import annotations

import argparse
from pathlib import Path


def add_subparser(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """Register `init` subparser and its flags."""
    p = subparsers.add_parser("init", help="Create starter configuration files.")
    p.add_argument(
        "--backend",
        choices=["sqlite", "mssql", "postgresql"],
        required=True,
    )
    p.add_argument("--output", type=Path, default=Path("mcp-tools-sql.toml"))
    p.add_argument(
        "--pyproject",
        action="store_true",
        help="Append [tool.mcp-tools-sql] to existing pyproject.toml.",
    )


def run(args: argparse.Namespace) -> int:
    """Entry point. Returns process exit code."""
    raise NotImplementedError("init: implemented in step 4")
