"""Output formatting helpers for query results."""

from __future__ import annotations

from typing import Any

from tabulate import tabulate


def format_rows(
    rows: list[dict[str, Any]],
    max_rows: int = 100,
) -> str:
    """Format query result rows as LLM-friendly tabular text.

    Args:
        rows: Query result rows as list of dicts.
        max_rows: Maximum rows to display. If len(rows) > max_rows,
                  output is truncated with a warning message.

    Returns:
        Formatted table string with column headers.
    """
    if not rows:
        return "No results found."
    total = len(rows)
    display_rows = rows[:max_rows]
    table = tabulate(display_rows, headers="keys", tablefmt="simple")
    if total > max_rows:
        table += f"\n\nShowing {max_rows} of {total} rows. Use filter to narrow."
    return table


def format_columns(
    columns: list[dict[str, Any]],
    max_rows: int,
    total_count: int,
) -> str:
    """Format column metadata as a human-readable string."""
    # TODO: render column info
    _ = columns, max_rows, total_count
    raise NotImplementedError


def format_update_result(
    affected_rows: int,
    table: str,
    key_value: Any,
) -> str:
    """Format the result of an update operation."""
    # TODO: render confirmation message
    _ = affected_rows, table, key_value
    raise NotImplementedError
