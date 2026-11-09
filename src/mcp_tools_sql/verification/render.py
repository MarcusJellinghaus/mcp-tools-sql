"""Text rendering of verify results: row formatting and the short summary."""

from __future__ import annotations

from typing import Literal

from mcp_tools_sql.verification._helpers import CheckResult, VerifyResult

STATUS_SYMBOLS: dict[str, str] = {"ok": "[OK]", "err": "[ERR]", "warn": "[WARN]"}
LABEL_WIDTH = 28  # minimum pad; longer labels are never truncated


def format_row(status: str, label: str, value: str = "", error: str = "") -> str:
    """Return one formatted row, e.g. ``[OK]  Python version  3.11.5``."""
    symbol = STATUS_SYMBOLS.get(status, status)
    parts = [symbol, label.ljust(LABEL_WIDTH)]
    if value:
        parts.append(value)
    if error:
        parts.append(f"- {error}")
    return "  ".join(parts).rstrip()


def row_status(entry: CheckResult) -> Literal["ok", "warn", "err"]:
    """Return the display status of one row: ``ok``, ``warn`` or ``err``."""
    if entry["ok"]:
        return "ok"
    if entry["severity"] == "warning":
        return "warn"
    return "err"


def render_short(result: VerifyResult) -> str:
    """Return the short summary: one summary line plus every ERR/WARN row.

    Rows are grouped under their ``=== TITLE ===`` header; sections with only
    passing rows are omitted.

    Returns:
        The rendered text, without a trailing newline.
    """
    lines = [_summary_line(result)]
    for section in result["sections"]:
        rows = [
            format_row(
                row_status(entry),
                label,
                entry.get("value", ""),
                entry.get("error", ""),
            )
            for label, entry in section["checks"].items()
            if row_status(entry) != "ok"
        ]
        if rows:
            lines.extend(["", f"=== {section['title']} ===", *rows])
    return "\n".join(lines)


def _summary_line(result: VerifyResult) -> str:
    """Return the first line of :func:`render_short`."""
    by_title = {section["title"]: section for section in result["sections"]}
    summary = result["summary"]

    config_section = by_title.get("CONFIG")
    config = (
        "Config loaded."
        if config_section is not None and config_section["ok"]
        else "Config has errors."
    )

    if "CONNECTION" not in by_title:
        connections = "not checked (targets unresolved)"
    else:
        up = [name for name, ok in summary["connections"].items() if ok]
        down = [name for name, ok in summary["connections"].items() if not ok]
        parts = []
        if up:
            parts.append(", ".join(up) + " reachable")
        if down:
            parts.append(", ".join(down) + " unreachable")
        connections = "; ".join(parts)

    def state(kind: str) -> str:
        if result["skipped_queries"] is not None:
            return "not checked (connection failed)"
        if kind not in by_title:
            return "not checked"
        return "OK" if by_title[kind]["ok"] else "with errors"

    queries = summary["query_count"]
    updates = summary["update_count"]
    query_state = state("QUERIES")
    update_state = state("UPDATES")
    if query_state == update_state:
        entries = f"{queries} queries, {updates} updates {query_state}"
    else:
        entries = f"{queries} queries {query_state}, {updates} updates {update_state}"
    if summary["allow_updates"] is False:
        entries += " (not exposed: allow_updates=false)"

    return f"{config} Connections: {connections}. {entries}."
