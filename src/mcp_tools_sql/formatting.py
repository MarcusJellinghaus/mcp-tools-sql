"""Output formatting helpers for query results."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from tabulate import tabulate

# Lowest meaningful row cap. Below 1 the cap is not merely useless but
# actively dangerous: ``rows[:-1]`` returns "all but the last |n| rows"
# instead of nothing, so a negative cap leaks nearly the whole result set.
# Every ``max_rows`` is floored at this bound before it reaches a slice.
MAX_ROWS_MIN: int = 1

# Appended to a statement-timeout message by tool-aware callers.
TIMEOUT_HINT_PARAMS = "Use more selective parameters."
TIMEOUT_HINT_NARROWER = "Use a narrower query."

# Why counting ended: end of data, ``max_count_rows``, the counting time
# limit, or the statement timeout.
StopReason = Literal["end", "max_count", "counting", "timeout"]


@dataclass
class SourceCount:
    """Matched-row count for one database of a limited read."""

    database: str
    matched: int = 0  # matched (post-filter) rows counted
    complete: bool = True  # False -> rendered as "N+"
    queried: bool = True  # False -> "not queried (...)"
    error: str = ""  # per-database error line
    timed_out: bool = False  # statement timeout before any matched row


@dataclass
class LimitedResult:
    """Display rows plus per-database counts produced by ``collect``."""

    rows: list[dict[str, str]]  # display rows, cells stringified/cut
    sources: list[SourceCount]  # config order
    display_limit: Literal["", "max_rows", "chars"] = ""
    stop: StopReason = "end"
    cells_cut: bool = False

    @property
    def total(self) -> int:
        """Matched rows counted across all sources."""
        return sum(s.matched for s in self.sources)

    @property
    def complete(self) -> bool:
        """True when every matched row was counted."""
        return self.stop == "end"


_OPERATOR_CHARS = "Operator: raise [limits] max_output_chars."
_OPERATOR_COLUMNS = (
    "Operator: select fewer columns in the configured SQL or raise "
    "[limits] max_output_chars."
)
_OPERATOR_HARD = "Operator: raise max_rows_hard in the query config."
_TIMEOUT_LABEL = "stopped: statement timeout"


def _total_text(matched: int, complete: bool) -> str:
    return f"{matched:,}" if complete else f"{matched:,}+"


def _next_steps(
    result: LimitedResult,
    *,
    max_rows: int,
    max_rows_hard: int,
    has_sql_params: bool,
    filter_column: str,
    builtin: bool,
) -> list[str]:
    """Return the next-step lines of the truncation message."""
    filter_phrase = f"narrow with {filter_column}_filter" if filter_column else ""
    steps: list[str] = []
    if result.display_limit == "chars":
        if not result.rows:
            steps.append(_OPERATOR_CHARS if builtin else _OPERATOR_COLUMNS)
        elif has_sql_params or filter_phrase:
            phrase = "filter with parameters" if has_sql_params else filter_phrase
            steps.append(f"To see different or fewer rows: {phrase}.")
        else:
            steps.append(_OPERATOR_CHARS)
    elif result.display_limit == "max_rows" or len(result.rows) >= max_rows:
        options: list[str] = []
        if max_rows < max_rows_hard:
            options.append(f"increase max_rows (hard limit {max_rows_hard:,})")
        if has_sql_params:
            options.append("refine parameters")
        elif filter_phrase:
            options.append(filter_phrase)
        if options:
            steps.append(f"To see more rows: {' or '.join(options)}.")
        elif not builtin:
            steps.append(_OPERATOR_HARD)
    if result.stop == "timeout" and has_sql_params:
        steps.append(TIMEOUT_HINT_PARAMS)
    return steps


def _truncation_message(
    result: LimitedResult, *, max_rows: int, max_output_chars: int
) -> str:
    """Return the head of the ``[Output truncated: ...]`` message."""
    total = _total_text(result.total, result.complete)
    if result.display_limit == "chars" and not result.rows:
        return (
            f"the first row is wider than the {max_output_chars:,}-char output "
            f"limit; showing 0 of {total} rows."
        )
    reasons: list[str] = []
    if result.display_limit == "chars":
        reasons.append(f"{max_output_chars:,}-char output limit reached")
    elif result.display_limit == "max_rows" or len(result.rows) >= max_rows:
        reasons.append(f"max_rows={max_rows} reached")
    if result.stop in ("max_count", "counting"):
        reasons.append("counting stopped")
    elif result.stop == "timeout":
        reasons.append(_TIMEOUT_LABEL)
    detail = f" ({'; '.join(reasons)})" if reasons else ""
    return f"showing {len(result.rows):,} of {total} rows{detail}."


def _matched_footer(result: LimitedResult) -> str:
    """Return the fan-out ``Matched: ...`` line ("" when no source qualifies)."""
    label = _TIMEOUT_LABEL if result.stop == "timeout" else "limit reached"
    parts: list[str] = []
    for src in result.sources:
        if src.error:
            continue
        if not src.queried:
            parts.append(f"{src.database} not queried ({label})")
        else:
            parts.append(f"{src.database} {_total_text(src.matched, src.complete)}")
    return f"Matched: {', '.join(parts)}." if parts else ""


def render_limited(  # pylint: disable=too-many-arguments
    result: LimitedResult,
    *,
    max_rows: int,
    max_rows_hard: int,
    has_sql_params: bool,
    filter_column: str,
    builtin: bool,
    fanout: bool,
    max_output_chars: int,
    max_cell_chars: int,
) -> str:
    """Render a :class:`LimitedResult` as the final tool text.

    Args:
        result: Display rows and per-database counts from ``collect``.
        max_rows: Effective (capped) ``max_rows``.
        max_rows_hard: Effective hard limit of the tool.
        has_sql_params: The resolved SQL has ``:placeholders``.
        filter_column: Column of the tool's ``*_filter``; "" when none.
        builtin: Built-in schema tool rather than a configured query.
        fanout: More than one target database.
        max_output_chars: ``[limits] max_output_chars``.
        max_cell_chars: ``[limits] max_cell_chars``.

    Returns:
        The table followed by the truncation message, fan-out footer,
        cell-cut line and per-database error lines, separated by blank
        lines; or the timeout message when a single target timed out
        before any row.
    """
    if not fanout and result.sources and result.sources[0].timed_out:
        error = result.sources[0].error
        return f"{error} {TIMEOUT_HINT_PARAMS}" if has_sql_params else error

    blocks: list[str] = [
        tabulate(result.rows, headers="keys", tablefmt="simple", disable_numparse=True)
        if result.rows
        else "No results found."
    ]
    truncated = len(result.rows) < result.total or not result.complete
    if truncated:
        head = _truncation_message(
            result, max_rows=max_rows, max_output_chars=max_output_chars
        )
        steps = _next_steps(
            result,
            max_rows=max_rows,
            max_rows_hard=max_rows_hard,
            has_sql_params=has_sql_params,
            filter_column=filter_column,
            builtin=builtin,
        )
        blocks.append(
            "[Output truncated: " + head + "".join("\n" + s for s in steps) + "]"
        )
    if fanout and (
        truncated or any(not s.complete or not s.queried for s in result.sources)
    ):
        footer = _matched_footer(result)
        if footer:
            blocks.append(footer)
    if result.cells_cut:
        blocks.append(f"Long values were cut at {max_cell_chars} chars.")
    errors = [f"{s.database}: {s.error}" for s in result.sources if s.error]
    if errors:
        blocks.append("\n".join(errors))
    return "\n\n".join(blocks)


def format_rows(
    rows: list[dict[str, Any]],
    max_rows: int = 100,
) -> str:
    """Format query result rows as LLM-friendly tabular text.

    Args:
        rows: Query result rows as list of dicts.
        max_rows: Maximum rows to display. If len(rows) > max_rows,
                  output is truncated with a warning message. Values below
                  :data:`MAX_ROWS_MIN` are raised to it.

    Returns:
        Formatted table string with column headers.
    """
    if not rows:
        return "No results found."
    max_rows = max(max_rows, MAX_ROWS_MIN)
    total = len(rows)
    display_rows = rows[:max_rows]
    table: str = tabulate(display_rows, headers="keys", tablefmt="simple")
    if total > max_rows:
        table += f"\n\nShowing {max_rows} of {total} rows."
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
        return f"No row found in {qualified_table} where {key_field}={key_value!r}."
    if affected_rows == 1:
        return f"Updated 1 row in {qualified_table} where {key_field}={key_value!r}."
    return (
        f"WARNING: key was supposed to uniquely identify one row\n"
        f"Updated {affected_rows} rows in {qualified_table} "
        f"where {key_field}={key_value!r}."
    )
