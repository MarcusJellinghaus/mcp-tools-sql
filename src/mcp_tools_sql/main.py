"""CLI entry point for mcp-tools-sql."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from mcp_tools_sql import __version__
from mcp_tools_sql.cli.commands import init, verify
from mcp_tools_sql.cli.parsers import HelpHintArgumentParser, WideHelpFormatter
from mcp_tools_sql.utils.log_utils import setup_logging

logger = logging.getLogger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    """Build the argument parser with subcommands.

    Returns:
        Configured argument parser.
    """
    parser = HelpHintArgumentParser(
        prog="mcp-tools-sql",
        description="MCP server for safe, configurable SQL database access.",
        formatter_class=WideHelpFormatter,
        add_help=False,
    )
    parser.add_argument(
        "--help",
        "-h",
        action="store_true",
        dest="help",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help=(
            "Path to project query config (default: auto-discovered via "
            "mcp-tools-sql.toml in the working directory)"
        ),
    )
    parser.add_argument(
        "--database-config",
        type=Path,
        default=None,
        help=(
            "Path to database configuration file (connections, credentials). "
            "Default: ~/.mcp-tools-sql/config.toml"
        ),
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Set the logging level (default: INFO)",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        default=None,
        help="Path to log file (default: stderr only)",
    )
    parser.add_argument(
        "--console-only",
        action="store_true",
        help="Disable file logging; log to stderr only",
    )

    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("help", help=argparse.SUPPRESS)
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

    if not args.command or args.command == "help" or args.help:
        parser.print_help()
        return 0

    log_file = None if args.console_only else args.log_file
    setup_logging(args.log_level, log_file)

    command = args.command

    if command == "server":
        raise NotImplementedError("server command not yet implemented")
    if command == "init":
        return init.run(args)
    if command == "verify":
        return verify.run(args)

    parser.print_help()
    return 1
