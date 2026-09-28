"""Cross-query count arithmetic in the renderers (``summarize/render.py``).

The profiling pipeline runs its count, scalar and value-list queries separately
with no snapshot, so a concurrent write can leave the renderer subtracting a
larger count from a smaller one. These cases build the skewed profiles by hand
and pin what the renderers print: a floor of zero, never a negative count and
never a suppressed line.
"""

from __future__ import annotations

from mcp_tools_sql.summarize.render import (
    ColumnProfile,
    render_deep,
    render_triage,
)
from mcp_tools_sql.summarize.sql import Category, ColumnMeta


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
    out = render_triage([_skewed_profile()], total_columns=1, distinct_gated=False)

    assert "0.0%" in out
    assert "-20.0%" not in out


def test_remainder_line_clamps_negative_rows_and_still_prints() -> None:
    """An over-counted top list prints a zero remainder, not a missing line."""
    profile = ColumnProfile(
        meta=_meta("city", "varchar", "other"),
        rows=100,
        non_null=100,
        distinct=10,
        stats={},
        values=[("a", 60), ("b", 60)],
        value_kind="top",
    )

    out = render_deep([profile])

    assert "    … 8 other values, 0 rows (0.0%)" in out.splitlines()
