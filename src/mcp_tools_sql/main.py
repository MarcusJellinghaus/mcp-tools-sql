"""CLI entry point for mcp-tools-sql."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

from mcp_tools_sql import __version__
from mcp_tools_sql.cli.commands import init, tool, verify
from mcp_tools_sql.cli.commands.help_config import CONFIG_GUIDE
from mcp_tools_sql.cli.parsers import HelpHintArgumentParser, WideHelpFormatter
from mcp_tools_sql.server import run_server
from mcp_tools_sql.utils.log_utils import OUTPUT, setup_logging
from mcp_tools_sql.utils.user_app_data import get_user_app_data_dir

logger = logging.getLogger(__name__)

_EPILOG = """\
With no command, runs the MCP server over stdio.

Getting started:
  mcp-tools-sql help config                  how to write the two config files
  mcp-tools-sql init --backend sqlite|mssql  write starter config files
  mcp-tools-sql verify                       check configs and connectivity
  mcp-tools-sql tool                         list and call tools directly
"""


def _build_parser() -> argparse.ArgumentParser:
    """Build the argument parser with subcommands.

    Returns:
        Configured argument parser.
    """
    parser = HelpHintArgumentParser(
        prog="mcp-tools-sql",
        description="MCP server for safe, configurable SQL database access.",
        epilog=_EPILOG,
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
            "Path to project query config (default: ./mcp-tools-sql.toml, "
            "else [tool.mcp-tools-sql] in ./pyproject.toml)"
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

    help_parser = subparsers.add_parser(
        "help", help="Show this help, or `help config` for the config file guide"
    )
    help_parser.add_argument("topic", nargs="?", choices=["config"])
    subparsers.add_parser("server", help="Start the MCP server (default).")
    init.add_subparser(subparsers)
    verify.add_subparser(subparsers)
    tool.add_subparser(subparsers)

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
    args, extras = parser.parse_known_args(argv if argv is not None else sys.argv[1:])
    if (args.command or "server") != "tool" and extras:
        parser.error("unrecognized arguments: " + " ".join(extras))

    if args.command == "help" and args.topic == "config":
        print(CONFIG_GUIDE, end="")
        return 0
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
            logger.error("%s", exc, exc_info=log_level == "DEBUG")
            logger.log(OUTPUT, "Try 'mcp-tools-sql verify' for diagnostics.")
            return 2
    if command == "init":
        return init.run(args)
    if command == "verify":
        return verify.run(args)
    if command == "tool":
        args.tool_argv = extras
        return tool.run(args)

    parser.print_help()
    return 1
