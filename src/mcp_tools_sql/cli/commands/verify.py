"""verify subcommand."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Any

from mcp_tools_sql.cli.parsers import WideHelpFormatter
from mcp_tools_sql.config.loader import (
    discover_query_config,
    load_database_config,
    load_query_config,
    resolve_connection,
)
from mcp_tools_sql.config.models import ConnectionConfig, QueryFileConfig
from mcp_tools_sql.verification import (
    verify_builtin,
    verify_config_files,
    verify_connection,
    verify_dependencies,
    verify_environment,
    verify_queries,
    verify_updates,
)
from mcp_tools_sql.verification._helpers import make_entry

logger = logging.getLogger(__name__)

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


def collect_install_instructions(
    sections: list[tuple[str, dict[str, Any]]],
) -> dict[str, Any]:
    """Aggregate non-empty ``install_hint`` strings from failed entries.

    Returns:
        Result dict with one entry per unique install hint, preserving
        the order in which they were first seen. ``overall_ok`` is always
        ``True`` because this section is informational.
    """
    hints: list[str] = []
    for _title, section in sections:
        for key, entry in section.items():
            if key == "overall_ok":
                continue
            hint = entry.get("install_hint", "")
            if hint and not entry["ok"]:
                hints.append(hint)

    unique_hints = list(dict.fromkeys(hints))
    result: dict[str, Any] = {
        f"hint_{i}": make_entry(ok=True, value=hint)
        for i, hint in enumerate(unique_hints)
    }
    result["overall_ok"] = True
    return result


def render_skip_m2_summary(query_count: int, update_count: int) -> str:
    """Return the one-line summary printed when M2 is skipped.

    Returns:
        ``"connection failed; skipped N query checks, M update checks"``.
    """
    return (
        f"connection failed; skipped {query_count} query checks, "
        f"{update_count} update checks"
    )


def _resolve_backend(
    config_path: Path | None,
    db_config_path: Path | None,
) -> str:
    """Best-effort backend resolution from configs.

    Returns:
        Backend name (e.g. ``sqlite``) or ``"unknown"`` on any failure.
    """
    try:
        resolved_query = discover_query_config(config_path, project_dir=Path.cwd())
        qcfg = load_query_config(resolved_query)
        dbcfg = load_database_config(db_config_path)
        conn = resolve_connection(qcfg, dbcfg)
        return conn.backend
    except (ValueError, OSError) as exc:
        logger.debug("Could not resolve backend: %s", exc)
        return "unknown"


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


def _resolve_connection_for_verify(
    config_path: Path | None,
    db_config_path: Path | None,
) -> ConnectionConfig | None:
    """Best-effort connection resolution for the CONNECTION section.

    Returns:
        Resolved :class:`ConnectionConfig`, or ``None`` if configs cannot
        be loaded or the named connection cannot be resolved.
    """
    try:
        resolved_query = discover_query_config(config_path, project_dir=Path.cwd())
        qcfg = load_query_config(resolved_query)
        dbcfg = load_database_config(db_config_path)
        return resolve_connection(qcfg, dbcfg)
    except (ValueError, OSError) as exc:
        logger.debug("Could not resolve connection: %s", exc)
        return None


def _load_query_config_for_counts(
    config_path: Path | None,
) -> tuple[int, int]:
    """Return ``(query_count, update_count)`` from the project query config.

    Returns:
        ``(0, 0)`` if the config cannot be loaded.
    """
    try:
        resolved_query = discover_query_config(config_path, project_dir=Path.cwd())
        qcfg = load_query_config(resolved_query)
        return len(qcfg.queries), len(qcfg.updates)
    except (ValueError, OSError) as exc:
        logger.debug("Could not load query config for counts: %s", exc)
        return 0, 0


def _load_query_config_for_m2(
    config_path: Path | None,
) -> QueryFileConfig | None:
    """Return the parsed :class:`QueryFileConfig` or ``None`` on failure."""
    try:
        resolved_query = discover_query_config(config_path, project_dir=Path.cwd())
        return load_query_config(resolved_query)
    except (ValueError, OSError) as exc:
        logger.debug("Could not load query config for M2: %s", exc)
        return None


def run(args: argparse.Namespace) -> int:
    """Entry point for the ``verify`` subcommand.

    Returns:
        Process exit code (``0`` if every section passed, ``1`` otherwise).
    """
    sections: list[tuple[str, dict[str, Any]]] = []
    sections.append(("ENVIRONMENT", verify_environment()))
    sections.append(
        (
            "CONFIG",
            verify_config_files(args.config, args.database_config),
        )
    )
    backend = _resolve_backend(args.config, args.database_config)
    sections.append(("DEPENDENCIES", verify_dependencies(backend)))
    sections.append(("BUILTIN", verify_builtin()))

    skip_summary: str | None = None
    connection = _resolve_connection_for_verify(args.config, args.database_config)
    if connection is not None:
        connection_result, open_backend = verify_connection(connection)
        sections.append(("CONNECTION", connection_result))
        try:
            if connection_result.get("overall_ok", False) and open_backend is not None:
                query_config = _load_query_config_for_m2(args.config)
                if query_config is not None:
                    sections.append(
                        (
                            "QUERIES",
                            verify_queries(
                                query_config.queries, connection.backend, open_backend
                            ),
                        )
                    )
                    sections.append(
                        (
                            "UPDATES",
                            verify_updates(
                                query_config.updates, connection.backend, open_backend
                            ),
                        )
                    )
            else:
                n_queries, n_updates = _load_query_config_for_counts(args.config)
                skip_summary = render_skip_m2_summary(n_queries, n_updates)
        finally:
            if open_backend is not None:
                open_backend.close()

    install_section = collect_install_instructions(sections)
    if any(key != "overall_ok" for key in install_section):
        sections.append(("INSTALL INSTRUCTIONS", install_section))

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
