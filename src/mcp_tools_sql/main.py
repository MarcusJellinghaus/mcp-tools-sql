"""CLI entry point for mcp-tools-sql."""

from __future__ import annotations

import argparse
import logging
import sys
import traceback
from datetime import datetime
from pathlib import Path

from mcp_tools_sql import __version__
from mcp_tools_sql.cli.commands import init, verify
from mcp_tools_sql.cli.parsers import HelpHintArgumentParser, WideHelpFormatter
from mcp_tools_sql.server import run_server
from mcp_tools_sql.utils.log_utils import OUTPUT, setup_logging
from mcp_tools_sql.utils.user_app_data import get_user_app_data_dir

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
        choices=["DEBUG", "INFO", "OUTPUT", "WARNING", "ERROR"],
        default=None,
        help="Set the logging level (default: INFO for server, OUTPUT for init/verify)",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        default=None,
        help=(
            "Path for structured JSON logs "
            "(default: mcp_tools_sql_{timestamp}.log in ~/.mcp-tools-sql/logs/)"
        ),
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


def _resolve_log_level(args: argparse.Namespace, command: str) -> str:
    """Resolve the effective log level for `command`.

    An explicit --log-level always wins. Otherwise `server` defaults to INFO
    (a full file trail) and the other commands to OUTPUT (clean console).

    Returns:
        The log level name to pass to setup_logging.
    """
    if args.log_level is not None:
        return str(args.log_level)
    return "INFO" if command == "server" else "OUTPUT"


def _resolve_log_file(args: argparse.Namespace, command: str) -> str | None:
    """Resolve the log-file path for `command`, or None for console-only.

    --console-only wins over an explicit --log-file. Only `server` gets a
    default file; init/verify stay console-only unless --log-file is given.

    Returns:
        Path to the log file as a string, or None when no file should be used.
    """
    if args.console_only:
        return None
    if args.log_file:
        return str(args.log_file)
    if command != "server":
        return None
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    logs_dir = get_user_app_data_dir("mcp-tools-sql") / "logs"
    return str(logs_dir / f"mcp_tools_sql_{timestamp}.log")


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and dispatch to the appropriate command.

    Returns:
        Process exit code.
    """
    parser = _build_parser()
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    if args.command == "help" or args.help:
        parser.print_help()
        return 0

    command = args.command or "server"
    log_level = _resolve_log_level(args, command)
    log_file = _resolve_log_file(args, command)
    setup_logging(log_level, log_file, console_level=OUTPUT if log_file else None)

    if command == "server":
        try:
            run_server(args)
            return 0
        except KeyboardInterrupt:
            return 130
        except (ValueError, OSError) as exc:
            logger.error("%s", exc)
            logger.log(OUTPUT, "Try 'mcp-tools-sql verify' for diagnostics.")
            if log_level == "DEBUG":
                traceback.print_exc()
            return 2
    if command == "init":
        return init.run(args)
    if command == "verify":
        return verify.run(args)

    parser.print_help()
    return 1
