"""Tests for the deep-view renderer (``summarize/render.py``).

Every case hand-builds a :class:`ColumnProfile` (no DB) and asserts on the
rendered text, pinning the issue's deep-view examples: labelled stat lines,
thousands separators, top-vs-sample value lists, the arithmetic remainder line,
and 60-character value truncation with exact counts.
"""

from __future__ import annotations

from mcp_tools_sql.summarize.render import (
    ColumnProfile,
    _fmt_int,
    _fmt_pct,
    _truncate,
    render_deep,
)
from mcp_tools_sql.summarize.sql import Category, ColumnMeta


def _meta(
    name: str, declared_type: str, category: Category, ordinal: int = 0
) -> ColumnMeta:
    return ColumnMeta(
        name=name, declared_type=declared_type, category=category, ordinal=ordinal
    )


def test_string_block_matches_customer_city_example() -> None:
    """String column with duplicates renders the issue's customer_city block."""
    profile = ColumnProfile(
        meta=_meta("customer_city", "varchar", "string"),
        rows=50_000,
        non_null=48_797,  # 50,000 - 1,203 nulls
        distinct=412,
        stats={"empty": 87, "len_min": 2, "len_max": 38, "len_avg": 11.4},
        values=[("London", 8_201), ("Paris", 6_110), (None, 1_203)],
        value_kind="top",
    )

    out = render_deep([profile])

    assert out.splitlines() == [
        "customer_city  (varchar, string)",
        "  rows 50,000 | nulls 1,203 (2.4%) | empty 87 (0.2%) | distinct 412",
        "  length  min 2 | max 38 | avg 11.4",
        "  top values:",
        "    London  8,201  (16.4%)",
        "    Paris  6,110  (12.2%)",
        "    NULL  1,203  (2.4%)",
        "    … 410 other values, 34,486 rows (69.0%)",
    ]


def test_near_unique_surfaces_duplicate_and_remainder() -> None:
    """distinct == non_null - 1: the duplicate is top, remainder present."""
    profile = ColumnProfile(
        meta=_meta("customer_email", "varchar", "string"),
        rows=101,
        non_null=101,
        distinct=100,
        stats={"empty": 0, "len_min": 9, "len_max": 34, "len_avg": 18.7},
        values=[("a.smith@example.com", 2), ("b.jones@example.com", 1)],
        value_kind="top",
    )

    out = render_deep([profile])

    assert "    a.smith@example.com  2  (2.0%)" in out
    assert "    … 98 other values, 98 rows (97.0%)" in out


def test_perfectly_unique_renders_sample_header_no_counts() -> None:
    """distinct == non_null: sample header names len(values), no counts."""
    profile = ColumnProfile(
        meta=_meta("order_reference", "varchar", "string"),
        rows=50_000,
        non_null=50_000,
        distinct=50_000,
        stats={"empty": 0, "len_min": 13, "len_max": 13, "len_avg": 13.0},
        values=[("ORD-000000001",), ("ORD-000000002",), ("ORD-000000003",)],
        value_kind="sample",
    )

    out = render_deep([profile])

    assert "  sample values (3 of 50,000 distinct — every value unique):" in out
    assert "    ORD-000000001" in out
    # No frequency/percentage columns in a sample list.
    assert "(%" not in out and "  1  " not in out


def test_sample_shown_count_is_len_values_not_requested_n() -> None:
    """A list capped below the requested n still reports the shown count.

    The renderer takes no ``n``; the header count is ``len(p.values)`` -- the 3
    rows the SQL actually returned -- so it can never claim ``999``.
    """
    profile = ColumnProfile(
        meta=_meta("token", "varchar", "string"),
        rows=3,
        non_null=3,
        distinct=3,
        stats={"empty": 0, "len_min": 5, "len_max": 5, "len_avg": 5.0},
        values=[("aaa",), ("bbb",), ("ccc",)],
        value_kind="sample",
    )

    out = render_deep([profile])

    assert "sample values (3 of 3 distinct" in out
    assert "999" not in out


def test_all_null_column_has_no_value_list() -> None:
    """non_null == 0, value_kind none: nulls reads 100.0%, no value list."""
    profile = ColumnProfile(
        meta=_meta("middle_name", "varchar", "string"),
        rows=1_000,
        non_null=0,
        distinct=0,
        stats={"empty": 0, "len_min": None, "len_max": None, "len_avg": None},
        values=None,
        value_kind="none",
    )

    out = render_deep([profile])

    assert "nulls 1,000 (100.0%)" in out
    assert "top values" not in out
    assert "sample values" not in out


def test_numeric_block_thousands_separators() -> None:
    """Numeric block: min/max/mean/sum/zero/neg with thousands separators."""
    profile = ColumnProfile(
        meta=_meta("amount_cents", "bigint", "numeric"),
        rows=50_000,
        non_null=49_000,
        distinct=8_000,
        stats={
            "min": 0,
            "max": 1_000_000,
            "mean": 523.7,
            "sum": 26_185_000,
            "zero": 12,
            "neg": 3,
        },
        values=[(100, 300), (200, 250)],
        value_kind="top",
    )

    lines = render_deep([profile]).splitlines()

    assert lines[0] == "amount_cents  (bigint, numeric)"
    assert lines[1] == ("  rows 50,000 | nulls 1,000 (2.0%) | distinct 8,000")
    assert lines[2] == "  min 0 | max 1,000,000 | mean 523.7 | sum 26,185,000"
    assert lines[3] == "  zeros 12 (0.0%) | negatives 3 (0.0%)"


def test_temporal_block_renders_bounds_verbatim() -> None:
    """Temporal min/max on their own line, no thousands-separator mangling."""
    profile = ColumnProfile(
        meta=_meta("order_date", "date", "temporal"),
        rows=2_020,
        non_null=2_020,
        distinct=365,
        stats={"min": "2020-01-01", "max": "2024-12-31"},
        values=[("2020-01-01", 10)],
        value_kind="top",
    )

    out = render_deep([profile])

    assert "  min 2020-01-01 | max 2024-12-31" in out
    assert "distinct 365" in out
    assert "2,020-" not in out  # the value itself is never separator-mangled


def test_boolean_block_true_false_null_shape() -> None:
    """Boolean stat line: true count + true% of rows, then false/null counts."""
    profile = ColumnProfile(
        meta=_meta("is_active", "bit", "boolean"),
        rows=250,
        non_null=220,
        distinct=2,
        stats={"true": 100, "false": 120},
        values=[(1, 120), (0, 100)],
        value_kind="top",
    )

    lines = render_deep([profile]).splitlines()

    assert lines[1] == "  rows 250 | nulls 30 (12.0%)"
    assert lines[2] == "  true 100 (40.0%) | false 120 | null 30"


def test_distinct_none_blanks_cell_and_omits_remainder() -> None:
    """distinct=None: cell reads em dash, top list omits the remainder line."""
    profile = ColumnProfile(
        meta=_meta("status", "varchar", "string"),
        rows=100,
        non_null=100,
        distinct=None,
        stats={"empty": 0, "len_min": 3, "len_max": 6, "len_avg": 4.2},
        values=[("open", 60), ("closed", 40)],
        value_kind="top",
    )

    out = render_deep([profile])

    assert "distinct —" in out
    assert "other values" not in out  # no remainder arithmetic on None


def test_sample_distinct_none_omits_of_clause() -> None:
    """A sample list with distinct=None drops the ``of D`` clause."""
    profile = ColumnProfile(
        meta=_meta("code", "varchar", "string"),
        rows=2,
        non_null=2,
        distinct=None,
        stats={"empty": 0, "len_min": 2, "len_max": 2, "len_avg": 2.0},
        values=[("AA",), ("BB",)],
        value_kind="sample",
    )

    out = render_deep([profile])

    assert "  sample values (2 distinct values):" in out
    assert " of " not in out


def test_other_block_size_line_present_and_absent() -> None:
    """``other`` renders the size line only when DATALENGTH stats are present."""
    with_size = ColumnProfile(
        meta=_meta("photo", "image", "other"),
        rows=10,
        non_null=8,
        distinct=None,
        stats={"size_min": 1_024, "size_max": 2_048_000, "size_avg": 512_000.5},
        values=None,
        value_kind="none",
    )
    without_size = ColumnProfile(
        meta=_meta("blob_col", "blob", "other"),
        rows=10,
        non_null=8,
        distinct=None,
        stats={},
        values=None,
        value_kind="none",
    )

    assert "  size (bytes)  min 1,024 | max 2,048,000 | avg 512,000.5" in render_deep(
        [with_size]
    )
    out = render_deep([without_size])
    assert "size (bytes)" not in out
    assert "distinct" not in out  # other never renders a distinct line


def test_render_deep_separates_blocks_with_blank_line() -> None:
    """Multiple profiles render as blank-line-separated blocks."""
    a = ColumnProfile(
        meta=_meta("a", "int", "numeric"),
        rows=1,
        non_null=1,
        distinct=1,
        stats={"min": 1, "max": 1, "mean": 1.0, "sum": 1, "zero": 0, "neg": 0},
        values=[(1, 1)],
        value_kind="sample",
    )
    b = ColumnProfile(
        meta=_meta("b", "int", "numeric"),
        rows=1,
        non_null=1,
        distinct=1,
        stats={"min": 2, "max": 2, "mean": 2.0, "sum": 2, "zero": 0, "neg": 0},
        values=[(2,)],
        value_kind="sample",
    )

    out = render_deep([a, b])

    assert "\n\n" in out
    assert out.count("(int, numeric)") == 2


def test_truncate_caps_at_60_chars() -> None:
    """A value over 60 chars is cut to 60 + ellipsis; counts stay exact."""
    long_value = "x" * 70

    result = _truncate(long_value)

    assert result == "x" * 60 + "…"
    assert len(result) == 61
    assert _truncate("x" * 60) == "x" * 60  # exactly at the cap, untouched


def test_truncate_renders_none_as_null() -> None:
    """``None`` renders literally as ``NULL`` (a top-values NULL row)."""
    assert _truncate(None) == "NULL"


def test_fmt_pct_guards_zero_whole() -> None:
    """A zero denominator does not raise; it renders ``(0.0%)``."""
    assert _fmt_pct(0, 0) == "(0.0%)"
    assert _fmt_pct(5, 0) == "(0.0%)"


def test_fmt_int_thousands_separator() -> None:
    """Sanity check on the shared integer formatter."""
    assert _fmt_int(1_234_567) == "1,234,567"
