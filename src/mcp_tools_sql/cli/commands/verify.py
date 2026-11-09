"""verify subcommand — thin CLI printer over mcp_tools_sql.verification."""

from __future__ import annotations

import argparse
import json

from mcp_tools_sql.cli.parsers import WideHelpFormatter
from mcp_tools_sql.verification import VerifyResult, verify_all
from mcp_tools_sql.verification._helpers import is_passing
from mcp_tools_sql.verification.orchestrator import render_skip_m2_summary
from mcp_tools_sql.verification.render import (
    LABEL_WIDTH,
    format_row,
    render_short,
    row_status,
)

# Old private names, kept for existing callers.
_LABEL_WIDTH = LABEL_WIDTH
_format_row = format_row


def _print_section(title: str) -> None:
    """Print a section header line."""
    print(f"=== {title} ===")


def _compute_exit_code(error_count: int) -> int:
    """Return ``0`` if no errors, ``1`` otherwise."""
    return 0 if error_count == 0 else 1


def _error_count(result: VerifyResult) -> int:
    """Return the number of ERR rows (rows that are not passing) in ``result``."""
    return sum(
        1
        for section in result["sections"]
        for entry in section["checks"].values()
        if not is_passing(entry)
    )


def add_subparser(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """Register the `verify` subparser and its ``--output-format`` flag."""
    parser = subparsers.add_parser(
        "verify",
        help=(
            "Validate environment, configuration, dependencies, and connectivity. "
            "Exit 0 on success, 1 on any error"
        ),
        formatter_class=WideHelpFormatter,
    )
    parser.add_argument(
        "--output-format",
        choices=["text", "json"],
        default="text",
        help="Output format: human-readable text (default) or the full result as JSON",
    )
    parser.add_argument(
        "--short",
        action="store_true",
        help="Text output only: one summary line plus the ERR/WARN rows by section",
    )


def run(args: argparse.Namespace) -> int:
    """Entry point for the ``verify`` subcommand.

    Returns:
        Process exit code (``0`` if every section passed, ``1`` otherwise).
    """
    result = verify_all(args.config, args.database_config)
    if getattr(args, "output_format", "text") == "json":
        print(json.dumps(result, indent=2))
        return _compute_exit_code(_error_count(result))
    if getattr(args, "short", False):
        print(render_short(result))
        return _compute_exit_code(_error_count(result))
    return _print_and_summarize(result)


def _print_and_summarize(result: VerifyResult) -> int:
    """Print every section's rows and the trailing summary line.

    Returns:
        Process exit code (0 if no errors, 1 otherwise).
    """
    ok_count = 0
    warn_count = 0
    for section in result["sections"]:
        _print_section(section["title"])
        for key, entry in section["checks"].items():
            status = row_status(entry)
            if status == "ok":
                print(_format_row("ok", key, entry.get("value", "")))
                ok_count += 1
                continue
            if status == "warn":
                warn_count += 1
            print(
                _format_row(status, key, entry.get("value", ""), entry.get("error", ""))
            )
        print()
    skipped_queries = result["skipped_queries"]
    if skipped_queries is not None:
        print(render_skip_m2_summary(skipped_queries, result["skipped_updates"] or 0))
    err_count = _error_count(result)
    print(f"{ok_count} checks passed, {warn_count} warnings, {err_count} errors")
    return _compute_exit_code(err_count)
