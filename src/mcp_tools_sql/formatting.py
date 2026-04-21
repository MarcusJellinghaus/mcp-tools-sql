"""Output formatting helpers for query results."""

from __future__ import annotations

from typing import Any


def format_rows(
    rows: list[dict[str, Any]],
    max_rows: int,
    total_count: int,
) -> str:
    """Format query result rows as a human-readable table string."""
    # TODO: render rows as aligned text or markdown table
    _ = rows, max_rows, total_count
    raise NotImplementedError


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
