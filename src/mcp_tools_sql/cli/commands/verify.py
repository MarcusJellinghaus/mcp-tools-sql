"""verify subcommand — thin CLI printer over mcp_tools_sql.verification."""

from __future__ import annotations

import argparse

from mcp_tools_sql.cli.parsers import WideHelpFormatter
from mcp_tools_sql.verification import VerifyResult, verify_all
from mcp_tools_sql.verification.orchestrator import render_skip_m2_summary

STATUS_SYMBOLS: dict[str, str] = {"ok": "[OK]", "err": "[ERR]", "warn": "[WARN]"}
_LABEL_WIDTH = 28  # minimum pad; longer labels are never truncated


def _format_row(status: str, label: str, value: str = "", error: str = "") -> str:
    """Return one formatted row, e.g. ``[OK]  Python version  3.11.5``."""
    symbol = STATUS_SYMBOLS.get(status, status)
    parts = [symbol, label.ljust(_LABEL_WIDTH)]
    if value:
        parts.append(value)
    if error:
        parts.append(f"- {error}")
    return "  ".join(parts).rstrip()


def _print_section(title: str) -> None:
    """Print a section header line."""
    print(f"=== {title} ===")


def _compute_exit_code(error_count: int) -> int:
    """Return ``0`` if no errors, ``1`` otherwise."""
    return 0 if error_count == 0 else 1


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
    """Entry point for the ``verify`` subcommand.

    Returns:
        Process exit code (``0`` if every section passed, ``1`` otherwise).
    """
    result = verify_all(args.config, args.database_config)
    return _print_and_summarize(result)


def _print_and_summarize(result: VerifyResult) -> int:
    """Print every section's rows and the trailing summary line.

    Returns:
        Process exit code (0 if no errors, 1 otherwise).
    """
    ok_count = 0
    warn_count = 0
    err_count = 0
    for section in result["sections"]:
        _print_section(section["title"])
        for key, entry in section["checks"].items():
            if not entry["ok"] and entry["severity"] == "warning":
                print(
                    _format_row(
                        "warn",
                        key,
                        entry.get("value", ""),
                        entry.get("error", ""),
                    )
                )
                warn_count += 1
            elif entry["ok"]:
                print(_format_row("ok", key, entry.get("value", "")))
                ok_count += 1
            else:
                print(
                    _format_row(
                        "err",
                        key,
                        entry.get("value", ""),
                        entry.get("error", ""),
                    )
                )
                err_count += 1
        print()
    skipped_queries = result["skipped_queries"]
    if skipped_queries is not None:
        print(render_skip_m2_summary(skipped_queries, result["skipped_updates"] or 0))
    print(f"{ok_count} checks passed, {warn_count} warnings, {err_count} errors")
    return _compute_exit_code(err_count)
