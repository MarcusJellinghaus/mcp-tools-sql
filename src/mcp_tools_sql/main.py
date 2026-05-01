"""CLI entry point for mcp-tools-sql."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

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

    # Default: run the MCP server
    subparsers.add_parser("server", help="Start the MCP server (default).")

    # Init: scaffold a new query config
    subparsers.add_parser("init", help="Create a starter query configuration file.")

    # Verify: validate config without starting the server
    subparsers.add_parser("verify", help="Validate configuration and exit.")

    return parser


def _setup_logging(level: str, log_file: Path | None, console_only: bool) -> None:
    """Configure logging based on CLI arguments."""
    # TODO: integrate with mcp-coder-utils logging setup
    _ = level, log_file, console_only


def main(argv: list[str] | None = None) -> None:
    """Parse arguments and dispatch to the appropriate command."""
    parser = _build_parser()
    args = parser.parse_args(argv or sys.argv[1:])

    _setup_logging(args.log_level, args.log_file, args.console_only)

    command = args.command or "server"

    if command == "server":
        # TODO: load config, create backend, start server
        raise NotImplementedError("server command not yet implemented")
    elif command == "init":
        # TODO: scaffold starter config
        raise NotImplementedError("init command not yet implemented")
    elif command == "verify":
        # TODO: validate config
        raise NotImplementedError("verify command not yet implemented")
    else:
        parser.print_help()
        sys.exit(1)
