"""CLI entry point for mcp-tools-sql."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from mcp_tools_sql.cli.commands import init, verify
from mcp_tools_sql.utils.log_utils import setup_logging

logger = logging.getLogger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    """Build the argument parser with subcommands.

    Returns:
        Configured argument parser.
    """
    parser = argparse.ArgumentParser(
        prog="mcp-tools-sql",
        description="MCP server for safe, configurable SQL database access.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to project query configuration file.",
    )
    parser.add_argument(
        "--database-config",
        type=Path,
        default=None,
        help="Path to database configuration file (connections, credentials).",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level.",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        default=None,
        help="Path to log file.",
    )
    parser.add_argument(
        "--console-only",
        action="store_true",
        help="Log to console only, skip file logging.",
    )

    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("server", help="Start the MCP server (default).")
    init.add_subparser(subparsers)
    verify.add_subparser(subparsers)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and dispatch to the appropriate command.

    Returns:
        Process exit code.
    """
    parser = _build_parser()
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    log_file = None if args.console_only else args.log_file
    setup_logging(args.log_level, log_file)

    command = args.command or "server"

    if command == "server":
        raise NotImplementedError("server command not yet implemented")
    if command == "init":
        return init.run(args)
    if command == "verify":
        return verify.run(args)

    parser.print_help()
    return 1
