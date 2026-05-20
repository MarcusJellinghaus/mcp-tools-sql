"""verify subcommand — thin CLI printer over mcp_tools_sql.verification."""

from __future__ import annotations

import argparse
from typing import Any

from mcp_tools_sql.cli.parsers import WideHelpFormatter
from mcp_tools_sql.verification import verify_all

STATUS_SYMBOLS: dict[str, str] = {"ok": "[OK]", "err": "[ERR]", "warn": "[WARN]"}
_LABEL_WIDTH = 28


def _pad(text: str, width: int) -> str:
    """Left-justify ``text`` to ``width`` (truncate if longer).

    Returns:
        The padded (or truncated) text, exactly ``width`` characters long.
    """
    if len(text) >= width:
        return text[:width]
    return text.ljust(width)


def _format_row(status: str, label: str, value: str = "", error: str = "") -> str:
    """Return one formatted row, e.g. ``[OK]  Python version  3.11.5``."""
    symbol = STATUS_SYMBOLS.get(status, status)
    parts = [symbol, _pad(label, _LABEL_WIDTH)]
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
    sections, skip_summary = verify_all(args.config, args.database_config)
    return _print_and_summarize(sections, skip_summary=skip_summary)


def _print_and_summarize(
    sections: list[tuple[str, dict[str, Any]]],
    *,
    skip_summary: str | None = None,
) -> int:
    """Print every section's rows and the trailing summary line.

    Returns:
        Process exit code (0 if no errors, 1 otherwise).
    """
    ok_count = 0
    warn_count = 0
    err_count = 0
    for title, result in sections:
        _print_section(title)
        for key, entry in result.items():
            if key == "overall_ok":
                continue
            if entry.get("warn"):
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
    if skip_summary is not None:
        print(skip_summary)
    print(f"{ok_count} checks passed, {warn_count} warnings, {err_count} errors")
    return _compute_exit_code(err_count)
