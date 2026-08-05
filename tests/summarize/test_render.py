"""Tests for the deep-view renderer (``summarize/render.py``).

Every case hand-builds a :class:`ColumnProfile` (no DB) and asserts on the
rendered text, pinning the issue's deep-view examples: labelled stat lines,
thousands separators, top-vs-sample value lists, the arithmetic remainder line,
and 60-character value truncation with exact counts.
"""

from __future__ import annotations

from mcp_tools_sql.summarize.render import (
    NO_COLUMNS_TEXT,
    ColumnProfile,
    _fmt_int,
    _fmt_pct,
    _truncate,
    column_cap_footer,
    empty_columns_message,
    empty_filter_message,
    empty_table_message,
    render_deep,
    render_summary,
    render_triage,
    table_not_found_message,
    unknown_columns_message,
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


def test_float_stats_round_to_one_decimal() -> None:
    """Non-round float stats render at one decimal, not full float precision."""
    string_profile = ColumnProfile(
        meta=_meta("customer_city", "varchar", "string"),
        rows=50_000,
        non_null=48_797,
        distinct=412,
        # 18.666666666666668 must render "18.7", never full float precision.
        stats={"empty": 0, "len_min": 2, "len_max": 38, "len_avg": 56 / 3},
        values=[("London", 8_201)],
        value_kind="top",
    )
    numeric_profile = ColumnProfile(
        meta=_meta("amount", "int", "numeric"),
        rows=3,
        non_null=3,
        distinct=3,
        # 10 / 3 == 3.3333... must render "3.3".
        stats={"min": 1, "max": 6, "mean": 10 / 3, "sum": 10, "zero": 0, "neg": 0},
        values=[(1, 1), (3, 1), (6, 1)],
        value_kind="top",
    )

    string_out = render_deep([string_profile])
    numeric_out = render_deep([numeric_profile])

    assert "avg 18.7" in string_out
    assert "18.666" not in string_out  # no full float precision leaks through
    assert "mean 3.3" in numeric_out
    assert "3.333" not in numeric_out


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


def _string_profile(name: str, distinct: int = 5) -> ColumnProfile:
    """A minimal string profile for triage/dispatch tests."""
    return ColumnProfile(
        meta=_meta(name, "varchar", "string"),
        rows=100,
        non_null=90,
        distinct=distinct,
        stats={
            "min": "aaa",
            "max": "zzz",
            "empty": 0,
            "len_min": 3,
            "len_max": 3,
            "len_avg": 3.0,
        },
        values=[("aaa", 50)],
        value_kind="top",
    )


def test_sixteen_profiles_dispatch_to_triage() -> None:
    """> 15 columns render the compact triage table, not deep blocks."""
    profiles = [_string_profile(f"c{i}") for i in range(16)]

    out = render_summary(profiles, total_columns=16, distinct_gated=False)

    # Triage header row from format_rows; no per-value list, no deep header.
    assert "null_pct" in out
    assert "top values" not in out
    assert "(varchar, string)" not in out
    assert out == render_triage(profiles, 16, False)


def test_fifteen_profiles_dispatch_to_deep() -> None:
    """At the threshold (15) the deep per-column blocks render."""
    profiles = [_string_profile(f"c{i}") for i in range(15)]

    out = render_summary(profiles, total_columns=15, distinct_gated=False)

    assert "(varchar, string)" in out
    assert "top values" in out
    assert out == render_deep(profiles)


def test_single_column_renders_deep_not_special_tier() -> None:
    """A 1-column call renders the same deep block, not a focus tier."""
    profiles = [_string_profile("only")]

    out = render_summary(profiles, total_columns=1, distinct_gated=False)

    assert out == render_deep(profiles)
    assert "(varchar, string)" in out


def test_render_summary_empty_returns_guard_sentence() -> None:
    """An empty profile list returns the defensive NO_COLUMNS_TEXT sentence."""
    out = render_summary([], total_columns=0, distinct_gated=False)

    assert out == NO_COLUMNS_TEXT
    assert out == "No columns to profile."
    assert out  # a non-empty sentence, not a blank string


def test_triage_cap_footer_reports_unshown_columns() -> None:
    """total_columns > len(profiles) appends the cap footer."""
    profiles = [_string_profile(f"c{i}") for i in range(50)]

    out = render_triage(profiles, total_columns=412, distinct_gated=False)

    assert "Showing 50 of 412 columns. Use columns= to select others." in out


def test_triage_gated_blanks_distinct_and_notes_reason() -> None:
    """distinct_gated blanks every distinct cell and states the 1M-row reason."""
    profiles = [_string_profile(f"c{i}", distinct=999) for i in range(16)]

    out = render_triage(profiles, total_columns=16, distinct_gated=True)

    assert "distinct omitted: table exceeds 1,000,000 rows." in out
    assert "999" not in out  # the gated distinct value never renders
    assert "—" in out  # distinct cells blank to the em dash


def test_triage_shows_value_min_max_per_category() -> None:
    """Numeric, temporal and string columns each render their value min/max."""
    numeric = ColumnProfile(
        meta=_meta("amount", "int", "numeric"),
        rows=100,
        non_null=100,
        distinct=40,
        stats={
            "min": 0,
            "max": 1_000_000,
            "mean": 5.0,
            "sum": 500,
            "zero": 0,
            "neg": 0,
        },
        values=None,
        value_kind="none",
    )
    temporal = ColumnProfile(
        meta=_meta("created", "date", "temporal"),
        rows=100,
        non_null=100,
        distinct=30,
        stats={"min": "2020-01-01", "max": "2024-12-31"},
        values=None,
        value_kind="none",
    )
    string = _string_profile("label")

    out = render_triage(
        [numeric, temporal, string], total_columns=3, distinct_gated=False
    )

    assert "1,000,000" in out  # numeric value max, separator applied
    assert "2020-01-01" in out and "2024-12-31" in out  # temporal bounds verbatim
    assert "aaa" in out and "zzz" in out  # string value bounds


def test_triage_boolean_and_other_blank_absent_min_max() -> None:
    """Boolean / other columns without min/max stats render em-dash cells."""
    boolean = ColumnProfile(
        meta=_meta("is_active", "bit", "boolean"),
        rows=100,
        non_null=100,
        distinct=2,
        stats={"true": 60, "false": 40},
        values=None,
        value_kind="none",
    )
    other = ColumnProfile(
        meta=_meta("photo", "image", "other"),
        rows=100,
        non_null=80,
        distinct=None,
        stats={},
        values=None,
        value_kind="none",
    )

    out = render_triage([boolean, other], total_columns=2, distinct_gated=False)

    assert "—" in out  # blanked min/max cells
    assert "None" not in out


def test_triage_ungated_none_distinct_blanks_without_literal_none() -> None:
    """An ungated other column with distinct=None still blanks the cell."""
    other = ColumnProfile(
        meta=_meta("blob_col", "varbinary", "other"),
        rows=100,
        non_null=100,
        distinct=None,
        stats={},
        values=None,
        value_kind="none",
    )

    out = render_triage([other], total_columns=1, distinct_gated=False)

    assert "—" in out
    assert "None" not in out  # the literal None never reaches tabulate


def test_empty_table_message_exact_wording() -> None:
    assert empty_table_message("dbo", "orders") == (
        "Table dbo.orders is empty (0 rows). "
        "Use read_columns for its column definitions."
    )


def test_table_not_found_message_distinct_from_empty() -> None:
    not_found = table_not_found_message("dbo", "orders")
    empty = empty_table_message("dbo", "orders")

    assert not_found == (
        "Table dbo.orders not found (no such table or no columns). "
        "Check the schema and table name."
    )
    assert not_found != empty  # not-found and empty are distinct messages


def test_empty_filter_message_exact_wording() -> None:
    assert empty_filter_message(50_000) == (
        "No rows match the where predicate (table has 50,000 rows)."
    )


def test_unknown_columns_message_echoes_casing_and_lists_available() -> None:
    out = unknown_columns_message(["Foo", "BAR"], ["id", "Name", "created_At"])

    assert out == "Unknown column(s): Foo, BAR. Available: id, Name, created_At"


def test_empty_columns_message_exact_wording() -> None:
    out = empty_columns_message(["id", "Name"])

    assert out == (
        "No columns selected: columns= was an empty list. Available: id, Name"
    )


def test_column_cap_footer_exact_wording() -> None:
    assert column_cap_footer(50, 412) == (
        "Showing 50 of 412 columns. Use columns= to select others."
    )
