"""Bounded collection of read-only results: filter, display budget, counting.

:func:`collect` is the single collection path for single-target and fan-out
(``database="*"``) reads. It pulls batches from each source, applies the
row filter, admits display rows under ``max_rows`` and the char budget,
cuts long cells, and counts matched rows until ``max_count_rows``, the
counting time limit, a statement timeout, or the end of data. Counted rows
beyond the display set are discarded, so memory stays at about the display
rows plus one batch.
"""

from __future__ import annotations

import copy
import time
from collections.abc import Callable, Generator
from dataclasses import dataclass
from typing import Any, Literal

from mcp_tools_sql.backends.base import Deadline, QueryTimeoutError
from mcp_tools_sql.config.models import LimitsConfig
from mcp_tools_sql.formatting import LimitedResult, SourceCount, StopReason

COUNTING_TIME_LIMIT_MAX: float = 5.0

# tabulate "simple" layout: headers are padded by MIN_PADDING, columns are
# separated by two spaces, and the header is followed by a separator line.
_HEADER_PADDING = 2
_COLUMN_GAP = 2
_HEADER_LINES = 2


@dataclass
class Source:
    """One database to read: a batch generator opened with the counting deadline."""

    database: str
    open: Callable[[Deadline], Generator[list[dict[str, Any]], None, None]]
    enforces_counting: bool = False  # backend interrupts at the counting deadline


def _identity(batch: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return batch


def counting_time_limit(timeout_seconds: int) -> float:
    """Return the counting time limit for a statement timeout.

    Args:
        timeout_seconds: The connection's ``query_timeout_seconds``.

    Returns:
        Half the statement timeout, capped at :data:`COUNTING_TIME_LIMIT_MAX`.
    """
    return min(COUNTING_TIME_LIMIT_MAX, timeout_seconds / 2)


def cell_text(value: Any, max_cell_chars: int) -> tuple[str, bool]:
    """Stringify a cell and cut it at *max_cell_chars*.

    Args:
        value: The raw cell value; ``None`` becomes ``""``.
        max_cell_chars: Longest text kept before the cut marker.

    Returns:
        Tuple ``(text, cut)``; *cut* is True when the value was shortened.
    """
    text = "" if value is None else str(value)
    if len(text) <= max_cell_chars:
        return text, False
    return f"{text[:max_cell_chars]}…[cut, {len(text):,} chars total]", True


class _CharBudget:
    """Tracks the rendered size of the display table as rows are admitted."""

    def __init__(self, max_chars: int) -> None:
        self._max_chars = max_chars
        self._widths: dict[str, int] = {}
        self._lines = _HEADER_LINES

    def admit(self, row: dict[str, str]) -> bool:
        """Admit *row* if the table including it stays within the budget.

        Returns:
            True when the row was admitted (and the running widths updated).
        """
        widths = dict(self._widths)
        height = 1
        for key, text in row.items():
            height = max(height, len(text.splitlines()))
            longest = max(len(part) for part in text.replace("\r", "\n").split("\n"))
            widths[key] = max(widths.get(key, len(key) + _HEADER_PADDING), longest)
        lines = self._lines + height
        width = sum(widths.values()) + _COLUMN_GAP * (len(widths) - 1)
        if lines * (width + 1) > self._max_chars:
            return False
        self._widths = widths
        self._lines = lines
        return True


def collect(  # pylint: disable=too-many-locals,too-many-branches,too-many-statements
    sources: list[Source],
    *,
    max_rows: int,
    limits: LimitsConfig,
    counting_seconds: float,
    filter_rows: Callable[[list[dict[str, Any]]], list[dict[str, Any]]] = _identity,
    record_errors: bool = False,
) -> LimitedResult:
    """Read *sources* in order under shared display and counting budgets.

    Args:
        sources: Databases to read, in config order.
        max_rows: Display rows shown across all sources.
        limits: ``[limits]`` settings (char budget, cell cut, count cap).
        counting_seconds: Counting time limit, started once the display set
            is complete.
        filter_rows: Applied to every raw batch; returns the matched rows.
        record_errors: Record non-timeout errors per source and continue
            (fan-out); when False they propagate (single target).

    Returns:
        The display rows, per-source counts and why collection stopped.
    """
    counting = Deadline()
    budget = _CharBudget(limits.max_output_chars)
    rows: list[dict[str, str]] = []
    counts: list[SourceCount] = []
    display_limit: Literal["", "max_rows", "chars"] = ""
    stop: StopReason = "end"
    cells_cut = False
    display_full = False
    counted = 0

    def _display_complete() -> None:
        nonlocal display_full
        display_full = True
        counting.at = time.monotonic() + counting_seconds

    for src in sources:
        if stop != "end":
            counts.append(SourceCount(src.database, queried=False, complete=False))
            continue
        count = SourceCount(src.database)
        counts.append(count)
        # Display state before this source, restored if it fails.
        rows_before = len(rows)
        budget_before = copy.copy(budget)
        display_before = (display_full, display_limit, cells_cut, counting.at)
        gen = src.open(counting)
        try:
            for batch in gen:
                for row in filter_rows(batch):
                    if counted == limits.max_count_rows:
                        stop = "max_count"  # this extra row proves "more"
                        if count.matched == 0:
                            count.queried = False
                        break
                    counted += 1
                    count.matched += 1
                    if display_full:
                        display_limit = display_limit or "max_rows"
                        continue
                    texts: dict[str, str] = {}
                    row_cut = False
                    for key, value in row.items():
                        texts[key], cut = cell_text(value, limits.max_cell_chars)
                        row_cut = row_cut or cut
                    if not budget.admit(texts):
                        display_limit = "chars"
                        _display_complete()
                        continue
                    rows.append(texts)
                    cells_cut = cells_cut or row_cut
                    if len(rows) >= max_rows:
                        _display_complete()
                if (
                    stop == "end"
                    and counting.at is not None
                    and time.monotonic() >= counting.at
                ):
                    stop = "counting"
                if stop != "end":
                    count.complete = False
                    break
        except QueryTimeoutError as exc:
            counting_passed = (
                counting.at is not None and time.monotonic() >= counting.at
            )
            stop = (
                "counting" if src.enforces_counting and counting_passed else "timeout"
            )
            count.complete = False
            if count.matched == 0 and stop == "timeout":
                count.error = str(exc)
                count.timed_out = True
            elif count.matched == 0:
                # Cut by the counting deadline before any match: nothing counted.
                count.queried = False
        except Exception as exc:  # pylint: disable=broad-exception-caught
            if not record_errors:
                raise
            count.error = str(exc)
            # The footer omits errored databases, so drop their partial count
            # and the display rows they contributed.
            counted -= count.matched
            count.matched = 0
            del rows[rows_before:]
            budget = budget_before
            display_full, display_limit, cells_cut, counting.at = display_before
        finally:
            gen.close()

    return LimitedResult(
        rows=rows,
        sources=counts,
        display_limit=display_limit,
        stop=stop,
        cells_cut=cells_cut,
    )
