"""Text renderers for the ``summarize_columns`` tool.

This module holds the summarize package's *presentation* layer. It is pure
formatting -- it never touches a backend or issues a query. It defines the
:class:`ColumnProfile` dataclass (the fully-assembled per-column result that
``tools.py`` builds from the metadata / scalar / value-list passes) and the
deep-view renderer :func:`render_deep`, which turns a list of profiles into one
labelled text block per column, the compact :func:`render_triage` table, the
:func:`render_summary` dispatcher that chooses between them on the column-count
threshold, and the zero-row / not-found / unknown-column status messages.

Every count printed is derived from the profile itself: the shown value count is
``len(profile.values)`` (the list the SQL layer already capped and returned) and
the remainder arithmetic reads ``profile.distinct`` and the returned frequencies.
No value-list length ``n`` is threaded in -- the SQL layer has already applied
the clamp and the ``LIMIT`` / ``TOP``, so a threaded ``n`` would be read by
nothing and could only disagree with what was actually returned.

Display values are truncated to 60 characters with a trailing ellipsis; the
*counts* beside them stay exact.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from mcp_tools_sql.formatting import format_rows
from mcp_tools_sql.summarize.sql import ColumnMeta

# Display cap for a single rendered value; longer values are truncated with an
# ellipsis. Counts printed alongside are never truncated.
_VALUE_DISPLAY_CAP: int = 60

# Decimal places for float stat cells (mean / len_avg / size_avg). Matches the
# contract's one-decimal examples (``avg 11.4``) rather than emitting full float
# precision (``18.666666666666668``).
_FLOAT_STAT_DECIMALS: int = 1

# Blank cell rendered when a stat is absent (all-null min/max) or a distinct
# count was gated out of triage (``ColumnProfile.distinct is None``).
_BLANK = "—"  # em dash

# Column-count threshold: a call profiling *more* than this many columns renders
# the compact triage view (one line per column); at or below it renders the deep
# per-column blocks.
TRIAGE_THRESHOLD: int = 15

# Hard cap on the number of columns profiled in a single call; the triage view
# appends a footer directing the caller to ``columns=`` for any beyond the cap.
COLUMN_CAP: int = 50

# Row-count ceiling above which triage omits ``COUNT(DISTINCT)`` (too costly on a
# large table); the distinct cells blank and the footer states the reason.
DISTINCT_GATE_ROWS: int = 1_000_000

# Defensive guard returned by :func:`render_summary` for an unexpectedly empty
# profile list (never reached in practice -- step 7 short-circuits first).
NO_COLUMNS_TEXT: str = "No columns to profile."


@dataclass(frozen=True)
class ColumnProfile:
    """Fully-assembled profiling result for one column, ready to render.

    Built in ``tools.py`` from the metadata query, the scalar-aggregate pass,
    and (deep view only) the per-column value-list query. Consumed by the
    renderers here and in the triage view; the renderers never re-derive any
    number from a backend.

    Attributes:
        meta: The column's metadata (declared casing / type / category /
            ordinal), carried through from the scalar pass.
        rows: The filtered ``COUNT(*)`` -- the same total for every column in a
            call, and the denominator for every percentage.
        non_null: ``COUNT(c)`` -- non-null tally; ``nulls`` is ``rows -
            non_null``.
        distinct: ``COUNT(DISTINCT c)``, or ``None`` when the distinct count was
            gated out (triage over a large table) or is inapplicable (``other``
            / LOB columns). A ``None`` renders as a blank cell and suppresses the
            top-values remainder arithmetic.
        stats: Category-specific aggregates keyed by stat suffix (``min``,
            ``max``, ``mean``, ``sum``, ``zero``, ``neg``, ``empty``,
            ``len_min`` / ``len_max`` / ``len_avg``, ``true`` / ``false``,
            ``size_min`` / ``size_max`` / ``size_avg``).
        values: The value-list rows -- ``(value, freq)`` tuples for a ``top``
            list, ``(value,)`` tuples for a ``sample`` list -- already capped by
            the SQL ``LIMIT`` / ``TOP``. ``None`` when no list was fetched.
        value_kind: ``"top"`` (frequency-ranked, has duplicates), ``"sample"``
            (distinct non-null values, every count 1), or ``"none"`` (no list:
            all-NULL columns and every ``other`` / binary column).
    """

    meta: ColumnMeta
    rows: int
    non_null: int
    distinct: int | None
    stats: dict[str, Any]
    values: list[tuple[Any, ...]] | None
    value_kind: Literal["top", "sample", "none"]


def _fmt_int(n: int) -> str:
    """Render an integer count with thousands separators (e.g. ``50,000``).

    Returns:
        The formatted integer string.
    """
    return f"{n:,}"


def _fmt_pct(part: int, whole: int) -> str:
    """Render ``part`` as a parenthesised percentage of ``whole``.

    Guards ``whole == 0`` (which cannot arise in the deep view -- it
    short-circuits on zero rows -- but keeps the helper total) by rendering
    ``(0.0%)`` rather than dividing by zero.

    Args:
        part: The numerator count.
        whole: The denominator count (typically ``ColumnProfile.rows``).

    Returns:
        A string like ``(2.4%)``.
    """
    if whole == 0:
        return "(0.0%)"
    return f"({part / whole * 100:.1f}%)"


def _truncate(value: Any) -> str:
    """Render a single value for display, capped at 60 characters.

    ``None`` renders as the literal ``NULL`` (so a ``NULL`` group in a
    top-values list is printed as a value row), and any value whose string form
    exceeds :data:`_VALUE_DISPLAY_CAP` characters is cut to the cap with a
    trailing ellipsis. Only the *display* is truncated -- the count printed
    beside the value stays exact.

    Args:
        value: The value to render (any type, including ``None``).

    Returns:
        The display string for ``value``.
    """
    if value is None:
        return "NULL"
    text = str(value)
    if len(text) > _VALUE_DISPLAY_CAP:
        return text[:_VALUE_DISPLAY_CAP] + "…"  # horizontal ellipsis
    return text


def _fmt_stat(value: Any) -> str:
    """Render an exact stat cell (min / max / sum / distinct / length bounds).

    Integers get thousands separators; floats keep their *exact* value with
    thousands separators and no forced rounding, so a numeric ``min`` of
    ``0.01`` or ``max`` of ``19.99`` is reported as-is rather than rounded away
    -- exactness matters for the extremes and totals a data-quality tool exists
    to surface. Averages (``mean`` / ``len_avg`` / ``size_avg``) are rendered by
    :func:`_fmt_avg` instead, which rounds to one decimal. Everything else
    (temporal bounds are date/time strings) is rendered verbatim so no separator
    is forced onto a value that is not a plain number, and a ``None`` (absent
    aggregate) renders as the blank cell.

    Args:
        value: The stat value from :attr:`ColumnProfile.stats` (or ``distinct``).

    Returns:
        The rendered cell text.
    """
    if value is None:
        return _BLANK
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return _fmt_int(value)
    if isinstance(value, float):
        return f"{value:,}"
    return str(value)


def _fmt_avg(value: Any) -> str:
    """Render an average cell (mean / len_avg / size_avg) at one decimal.

    Averages are the only stats rounded: they carry no meaning past a fraction,
    and full float precision (``18.666666666666668``) is noise. Rounds floats to
    :data:`_FLOAT_STAT_DECIMALS` decimal place(s) with thousands separators (so
    ``11.4`` matches the contract examples); integers and ``None`` fall back to
    the shared integer / blank handling.

    Args:
        value: The average value from :attr:`ColumnProfile.stats`.

    Returns:
        The rendered cell text.
    """
    if value is None:
        return _BLANK
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return _fmt_int(value)
    if isinstance(value, float):
        return f"{value:,.{_FLOAT_STAT_DECIMALS}f}"
    return str(value)


def _numeric_lines(p: ColumnProfile, rows: int, nulls: int) -> list[str]:
    """Stat lines for a numeric column: counts, then bounds, then zero/neg.

    Returns:
        The produced stat lines for the numeric column.
    """
    s = p.stats
    zero = s.get("zero", 0)
    neg = s.get("neg", 0)
    return [
        f"  rows {_fmt_int(rows)} | nulls {_fmt_int(nulls)} {_fmt_pct(nulls, rows)}"
        f" | distinct {_fmt_stat(p.distinct)}",
        f"  min {_fmt_stat(s.get('min'))} | max {_fmt_stat(s.get('max'))}"
        f" | mean {_fmt_avg(s.get('mean'))} | sum {_fmt_stat(s.get('sum'))}",
        f"  zeros {_fmt_int(zero)} {_fmt_pct(zero, rows)}"
        f" | negatives {_fmt_int(neg)} {_fmt_pct(neg, rows)}",
    ]


def _temporal_lines(p: ColumnProfile, rows: int, nulls: int) -> list[str]:
    """Stat lines for a temporal column: counts, then min/max date bounds.

    Returns:
        The produced stat lines for the temporal column.
    """
    s = p.stats
    return [
        f"  rows {_fmt_int(rows)} | nulls {_fmt_int(nulls)} {_fmt_pct(nulls, rows)}"
        f" | distinct {_fmt_stat(p.distinct)}",
        f"  min {_fmt_stat(s.get('min'))} | max {_fmt_stat(s.get('max'))}",
    ]


def _string_lines(p: ColumnProfile, rows: int, nulls: int) -> list[str]:
    """Stat lines for a string column: counts (+empty), then char lengths.

    Returns:
        The produced stat lines for the string column.
    """
    s = p.stats
    empty = s.get("empty", 0)
    return [
        f"  rows {_fmt_int(rows)} | nulls {_fmt_int(nulls)} {_fmt_pct(nulls, rows)}"
        f" | empty {_fmt_int(empty)} {_fmt_pct(empty, rows)}"
        f" | distinct {_fmt_stat(p.distinct)}",
        f"  length  min {_fmt_stat(s.get('len_min'))}"
        f" | max {_fmt_stat(s.get('len_max'))} | avg {_fmt_avg(s.get('len_avg'))}",
    ]


def _boolean_lines(p: ColumnProfile, rows: int, nulls: int) -> list[str]:
    """Stat lines for a boolean column: counts, then true/false/null tally.

    ``true %`` is of ``rows``; ``false`` and ``null`` carry no second
    percentage -- with a boolean partition it would be redundant.

    Returns:
        The produced stat lines for the boolean column.
    """
    s = p.stats
    true = s.get("true", 0)
    false = s.get("false", 0)
    return [
        f"  rows {_fmt_int(rows)} | nulls {_fmt_int(nulls)} {_fmt_pct(nulls, rows)}",
        f"  true {_fmt_int(true)} {_fmt_pct(true, rows)}"
        f" | false {_fmt_int(false)} | null {_fmt_int(nulls)}",
    ]


def _other_lines(p: ColumnProfile, rows: int, nulls: int) -> list[str]:
    """Stat lines for an ``other`` / binary column: counts, then byte size.

    The ``size (bytes)`` line is emitted only when the ``DATALENGTH``
    aggregates are present (T-SQL); on SQLite those stats are absent and the
    line is omitted. There is never a distinct line for this category.

    Returns:
        The produced stat lines for the ``other`` / binary column.
    """
    s = p.stats
    lines = [
        f"  rows {_fmt_int(rows)} | nulls {_fmt_int(nulls)} {_fmt_pct(nulls, rows)}"
    ]
    if "size_min" in s:
        lines.append(
            f"  size (bytes)  min {_fmt_stat(s['size_min'])}"
            f" | max {_fmt_stat(s['size_max'])} | avg {_fmt_avg(s['size_avg'])}"
        )
    return lines


# Per-category stat-line builders, keyed on ``ColumnMeta.category``.
_STAT_DISPATCH = {
    "numeric": _numeric_lines,
    "temporal": _temporal_lines,
    "string": _string_lines,
    "boolean": _boolean_lines,
    "other": _other_lines,
}


def _render_values(p: ColumnProfile) -> list[str]:
    """Render a column's value-list section (empty for ``value_kind == "none"``).

    For a ``top`` list: a ``top values:`` header, one ``value  freq  (pct)`` row
    per returned value (``NULL`` printed literally), then -- only when
    ``distinct`` is known -- a remainder line giving the values and rows not
    shown. The remainder is pure arithmetic: because ``COUNT(DISTINCT)`` excludes
    nulls while the list ranks ``NULL`` as a row, the distinct remainder counts
    only the *non-null* values shown.

    For a ``sample`` list: a header naming the shown count and (when known) the
    distinct total, then the values with no counts. The shown count is
    ``len(p.values)`` -- the rows the SQL actually returned, already capped --
    never a requested ``n``.

    Args:
        p: The profile whose value list to render.

    Returns:
        The value-list lines, or ``[]`` when there is no list to show.
    """
    if p.value_kind == "none" or not p.values:
        return []
    values = p.values
    rows = p.rows
    if p.value_kind == "top":
        lines = ["  top values:"]
        shown_rows = sum(freq for _, freq in values)
        shown_nonnull_distinct = len([v for v, _ in values if v is not None])
        for value, freq in values:
            lines.append(
                f"    {_truncate(value)}  {_fmt_int(freq)}  {_fmt_pct(freq, rows)}"
            )
        if p.distinct is not None:
            rem_vals = p.distinct - shown_nonnull_distinct
            rem_rows = rows - shown_rows
            if rem_vals > 0:
                lines.append(
                    f"    … {_fmt_int(rem_vals)} other values, "
                    f"{_fmt_int(rem_rows)} rows {_fmt_pct(rem_rows, rows)}"
                )
        return lines
    # sample
    if p.distinct is not None:
        header = (
            f"  sample values ({_fmt_int(len(values))} of {_fmt_int(p.distinct)}"
            f" distinct — every value unique):"
        )
    else:
        header = f"  sample values ({_fmt_int(len(values))} distinct values):"
    lines = [header]
    for row in values:
        lines.append(f"    {_truncate(row[0])}")
    return lines


def _render_block(p: ColumnProfile) -> str:
    """Render one column's full labelled block: header, stats, value list.

    The header carries the column's inline :attr:`ColumnMeta.note` after the
    category when one is set (``(unknown, string — type not determined: …)``);
    with the usual empty note the header is unchanged.

    Args:
        p: The profile to render.

    Returns:
        The block as a single newline-joined string (no trailing blank line).
    """
    meta = p.meta
    nulls = p.rows - p.non_null
    note = f" — {meta.note}" if meta.note else ""
    lines = [f"{meta.name}  ({meta.declared_type}, {meta.category}{note})"]
    lines += _STAT_DISPATCH[meta.category](p, p.rows, nulls)
    lines += _render_values(p)
    return "\n".join(lines)


def render_deep(profiles: list[ColumnProfile]) -> str:
    """Render the deep view: one full labelled block per profiled column.

    Blocks are separated by a blank line. Pure formatting -- no backend is
    touched and every printed count is derived from the profiles themselves.

    Args:
        profiles: The profiled columns, in output order.

    Returns:
        The rendered deep view as a single string.
    """
    return "\n\n".join(_render_block(p) for p in profiles)


def _pct_cell(part: int, whole: int) -> str:
    """Render a bare percentage for a triage table cell (no parentheses).

    The deep view wraps percentages in parentheses (``(2.4%)``); a table cell
    reads cleaner unwrapped (``2.4%``). Guards ``whole == 0`` (unreachable --
    triage short-circuits on zero rows -- but keeps the helper total).

    Args:
        part: The numerator count (typically the null tally).
        whole: The denominator count (typically ``ColumnProfile.rows``).

    Returns:
        A string like ``2.4%``.
    """
    if whole == 0:
        return "0.0%"
    return f"{part / whole * 100:.1f}%"


def render_triage(
    profiles: list[ColumnProfile], total_columns: int, distinct_gated: bool
) -> str:
    """Render the compact triage view: one tabular line per profiled column.

    Each column contributes a row with its name, declared type, null
    percentage, distinct count, and value min/max -- no value lists. The
    ``distinct`` cell blanks to :data:`_BLANK` whenever it is unknown: the whole
    view is gated (``distinct_gated``), or an individual profile carries
    ``distinct is None`` (``other`` / LOB columns, which cannot be counted
    distinctly). ``min`` / ``max`` blank the same way when the scalar pass did
    not compute them (boolean and other columns), and are truncated to
    :data:`_VALUE_DISPLAY_CAP` characters -- string value bounds surface only
    here, and one long value would pad every row of the table. The literal
    string ``None`` never reaches the table -- every optional cell passes
    through a blanking helper.

    Footers: a column-cap notice when ``total_columns`` exceeds the number of
    profiles shown, a hint that a narrowed ``columns=`` call yields the deep
    per-column view, and -- when gated -- the row-count reason distinct was
    omitted.

    Args:
        profiles: The profiled columns, in output order (already capped).
        total_columns: The number of columns the call selected before the cap
            -- the table's full profilable column count for an unfiltered call,
            or the requested count when ``columns=`` narrowed it (for the cap
            footer).
        distinct_gated: Whether the distinct count was gated out for the whole
            call (large table).

    Returns:
        The rendered triage view as a single string.
    """
    rows: list[dict[str, Any]] = []
    for p in profiles:
        nulls = p.rows - p.non_null
        rows.append(
            {
                "name": p.meta.name,
                "type": p.meta.declared_type,
                "null_pct": _pct_cell(nulls, p.rows),
                "distinct": _BLANK if distinct_gated else _fmt_stat(p.distinct),
                "min": _truncate(_fmt_stat(p.stats.get("min"))),
                "max": _truncate(_fmt_stat(p.stats.get("max"))),
            }
        )
    table = format_rows(rows, max_rows=COLUMN_CAP)

    footers: list[str] = []
    if total_columns > len(profiles):
        footers.append(column_cap_footer(len(profiles), total_columns))
    footers.append(
        f"Narrow with columns= (≤ {TRIAGE_THRESHOLD} columns) for the deep "
        "per-column view."
    )
    if distinct_gated:
        footers.append(
            f"distinct omitted: table exceeds {_fmt_int(DISTINCT_GATE_ROWS)} rows."
        )
    return table + "\n\n" + "\n".join(footers)


def render_summary(
    profiles: list[ColumnProfile], total_columns: int, distinct_gated: bool
) -> str:
    """Dispatch to the triage or deep renderer on the column-count threshold.

    More than :data:`TRIAGE_THRESHOLD` profiles render the compact triage view;
    at or below it render the deep per-column blocks (a 1-column call renders
    the same deep block as one of ten -- there is no focus tier). An empty
    profile list returns the fixed :data:`NO_COLUMNS_TEXT` sentence: a defensive
    guard, not a reachable path (step 7 rejects an empty ``columns=`` and
    short-circuits zero rows before any data query).

    Args:
        profiles: The profiled columns, in output order.
        total_columns: The number of columns the call selected before the cap
            -- the table's full profilable column count for an unfiltered call,
            or the requested count when ``columns=`` narrowed it (triage cap
            footer).
        distinct_gated: Whether the distinct count was gated out (triage).

    Returns:
        The rendered summary as a single string.
    """
    if not profiles:
        return NO_COLUMNS_TEXT
    if len(profiles) > TRIAGE_THRESHOLD:
        return render_triage(profiles, total_columns, distinct_gated)
    return render_deep(profiles)


def empty_source_message(label: str | None) -> str:
    """Message for a source that resolved but holds zero rows.

    A labelled source is a persisted table, so the wording keeps the table
    phrasing and the ``read_columns`` pointer; an unlabelled one is a user
    query, for which neither applies.

    Args:
        label: The source descriptor (``schema.table``), or ``None`` for a
            query source.

    Returns:
        The empty-source message string.
    """
    if label is None:
        return "The source query returned 0 rows."
    return (
        f"Table {label} is empty (0 rows). "
        "Use read_columns for its column definitions."
    )


def table_not_found_message(schema: str, table: str) -> str:
    """Message for a table whose metadata query returned no columns.

    Returns:
        The table-not-found message string.
    """
    return (
        f"Table {schema}.{table} not found (no such table or no columns). "
        "Check the schema and table name."
    )


def empty_filter_message(total_rows: int, label: str | None) -> str:
    """Message when the ``where`` predicate matches no rows.

    Args:
        total_rows: The unfiltered row count of the source.
        label: The source descriptor (``schema.table``), or ``None`` for a
            query source -- which decides whether the count is attributed to a
            "table" or to the "source".

    Returns:
        The empty-filter message string.
    """
    subject = "table" if label is not None else "source"
    return (
        "No rows match the where predicate "
        f"({subject} has {_fmt_int(total_rows)} rows)."
    )


def unknown_columns_message(bad: list[str], available: list[str]) -> str:
    """Message listing unrecognised requested columns and the available set.

    Both lists echo the declared casing carried through from the metadata
    query.

    Returns:
        The unknown-columns message string.
    """
    return f"Unknown column(s): {', '.join(bad)}. Available: {', '.join(available)}"


def empty_columns_message(available: list[str]) -> str:
    """Message for an explicitly empty ``columns=[]`` request.

    Returns:
        The empty-columns message string.
    """
    return (
        "No columns selected: columns= was an empty list. "
        f"Available: {', '.join(available)}"
    )


def column_cap_footer(shown: int, total: int) -> str:
    """Footer stating how many of the table's columns the cap left unshown.

    Returns:
        The column-cap footer string.
    """
    return (
        f"Showing {_fmt_int(shown)} of {_fmt_int(total)} columns. "
        "Use columns= to select others."
    )
