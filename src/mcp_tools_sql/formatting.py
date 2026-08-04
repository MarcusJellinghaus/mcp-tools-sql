"""Output formatting helpers for query results."""

from __future__ import annotations

from typing import Any

from tabulate import tabulate


def format_rows(
    rows: list[dict[str, Any]],
    max_rows: int = 100,
    truncation_hint: str = "",
) -> str:
    """Format query result rows as LLM-friendly tabular text.

    Args:
        rows: Query result rows as list of dicts.
        max_rows: Maximum rows to display. If len(rows) > max_rows,
                  output is truncated with a warning message.
        truncation_hint: Optional suffix appended after the count line
                  when truncation occurs. Empty string suppresses it.

    Returns:
        Formatted table string with column headers.
    """
    if not rows:
        return "No results found."
    total = len(rows)
    display_rows = rows[:max_rows]
    table: str = tabulate(display_rows, headers="keys", tablefmt="simple")
    if total > max_rows:
        suffix = f" {truncation_hint}" if truncation_hint else ""
        table += f"\n\nShowing {max_rows} of {total} rows.{suffix}"
    return table


def format_fanout_rows(
    rows: list[dict[str, Any]],
    counts: dict[str, int],
    errors: list[tuple[str, str]],
    max_rows: int = 100,
    truncation_hint: str = "",
) -> str:
    """Format merged fan-out (``database="*"``) result rows.

    Args:
        rows: Merged rows from every fanned-out database, in config order.
            Each row carries a ``_database`` source column.
        counts: Exact per-database row counts (config order), used to render
            the truncation footer breakdown.
        errors: ``(database, message)`` pairs for databases that failed; each
            is rendered inline on its own line rather than raised.
        max_rows: Maximum rows to display before the merged list is truncated.
        truncation_hint: Optional suffix appended after the footer count line
            when truncation occurs. Empty string suppresses it.

    Returns:
        Formatted table string. When a single database succeeded with no
        errors, delegates to :func:`format_rows` for byte-identical output;
        otherwise renders the table plus a per-database truncation footer
        (only on truncation) and one line per errored database.
    """
    if len(counts) <= 1 and not errors:
        return format_rows(rows, max_rows, truncation_hint=truncation_hint)

    total = len(rows)
    table: str = (
        tabulate(rows[:max_rows], headers="keys", tablefmt="simple")
        if rows
        else "No results found."
    )

    if total > max_rows:
        matched = ", ".join(f"{db} {n}" for db, n in counts.items())
        suffix = f" {truncation_hint}" if truncation_hint else ""
        table += f"\n\nShowing {max_rows} of {total} rows. Matched: {matched}.{suffix}"

    if errors:
        error_lines = "\n".join(f"{db}: {msg}" for db, msg in errors)
        table += f"\n\n{error_lines}"

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
    qualified_table: str,
    key_field: str,
    key_value: Any,
) -> str:
    """Format the result of an update operation.

    Returns:
        A human-readable message describing how many rows were affected.
    """
    if affected_rows == 0:
        return f"No row found in {qualified_table} where " f"{key_field}={key_value!r}."
    if affected_rows == 1:
        return (
            f"Updated 1 row in {qualified_table} where " f"{key_field}={key_value!r}."
        )
    return (
        f"WARNING: key was supposed to uniquely identify one row\n"
        f"Updated {affected_rows} rows in {qualified_table} "
        f"where {key_field}={key_value!r}."
    )
