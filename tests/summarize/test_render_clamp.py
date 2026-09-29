"""Cross-query count arithmetic in the renderers (``summarize/render.py``).

The profiling pipeline runs its count, scalar and value-list queries separately
with no snapshot, so a concurrent write can leave the renderer subtracting a
larger count from a smaller one. These cases build the skewed profiles by hand
and pin what the renderers print: a floor of zero, never a negative count and
never a suppressed line. The last case drives the whole tool, pinning the
clamped line and the footer note that explains it as one output.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from mcp_tools_sql.summarize.render import (
    ColumnProfile,
    inconsistent_counts_note,
    render_deep,
    render_triage,
)
from mcp_tools_sql.summarize.sql import Category, ColumnMeta
from tests.summarize.tool_helpers import call_summarize, client_for


def _meta(
    name: str, declared_type: str, category: Category, ordinal: int = 0
) -> ColumnMeta:
    return ColumnMeta(
        name=name, declared_type=declared_type, category=category, ordinal=ordinal
    )


def _skewed_profile() -> ColumnProfile:
    """Build a profile whose non-null tally exceeds its row count.

    Returns:
        A profile with ``rows=100`` and ``non_null=120`` and no value list.
    """
    return ColumnProfile(
        meta=_meta("payload", "varbinary", "other"),
        rows=100,
        non_null=120,
        distinct=None,
        stats={},
        values=None,
        value_kind="none",
    )


def test_deep_block_clamps_negative_nulls() -> None:
    """non_null > rows cannot print a negative null count."""
    out = render_deep([_skewed_profile()])

    assert "nulls 0 (0.0%)" in out
    assert "-20" not in out


def test_triage_clamps_negative_nulls() -> None:
    """The triage null percentage clamps with the count it is derived from."""
    out = render_triage([_skewed_profile()], total_columns=1)

    assert "0.0%" in out
    assert "-20.0%" not in out


def test_remainder_line_clamps_negative_rows_and_still_prints() -> None:
    """An over-counted top list prints a zero remainder, not a missing line."""
    profile = ColumnProfile(
        meta=_meta("city", "varchar", "string"),
        rows=100,
        non_null=100,
        distinct=10,
        stats={},
        values=[("a", 60), ("b", 60)],
        value_kind="top",
    )

    out = render_deep([profile])

    assert "    … 8 other values, 0 rows (0.0%)" in out.splitlines()


def _over_counted_backend() -> MagicMock:
    """Return a backend whose top-list frequencies outrun its own row count.

    One numeric column, ``COUNT(*)`` of 100, ``COUNT(c)`` of 100 and
    ``COUNT(DISTINCT c)`` of 10, then a value list whose two rows carry 60
    occurrences each -- the shape a concurrent insert leaves behind between the
    count query and the value-list query.

    Returns:
        The configured :class:`MagicMock` backend.
    """

    def fake(sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        if "pragma_table_info" in sql or "INFORMATION_SCHEMA" in sql:
            return [{"name": "qty", "type": "INTEGER", "ordinal": 0}]
        if "row_count" in sql:
            return [{"row_count": 100}]
        if "c0__nonnull" in sql:
            return [
                {
                    "c0__nonnull": 100,
                    "c0__distinct": 10,
                    "c0__min": 1,
                    "c0__max": 5,
                    "c0__mean": 3.0,
                    "c0__sum": 300,
                    "c0__zero": 0,
                    "c0__neg": 0,
                }
            ]
        return [{"value": 1, "freq": 60}, {"value": 2, "freq": 60}]

    backend = MagicMock()
    backend.execute_readonly_query.side_effect = fake
    return backend


@pytest.mark.asyncio
async def test_clamped_remainder_prints_beside_the_skew_note() -> None:
    """The zero remainder and the note explaining it arrive in one output."""
    async with client_for(_over_counted_backend()) as client:
        out = await call_summarize(client, "main", "big")

    assert "    … 8 other values, 0 rows (0.0%)" in out.splitlines()
    assert out.endswith(inconsistent_counts_note())
