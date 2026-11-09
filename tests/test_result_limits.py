"""Tests for ``result_limits.collect`` and its helpers."""

from __future__ import annotations

import time
from collections.abc import Callable, Generator
from pathlib import Path
from typing import Any

import pytest
from tabulate import tabulate

from mcp_tools_sql.backends.base import Deadline, QueryTimeoutError
from mcp_tools_sql.backends.sqlite import SQLiteBackend
from mcp_tools_sql.config.models import ConnectionConfig, LimitsConfig
from mcp_tools_sql.formatting import render_limited
from mcp_tools_sql.result_limits import (
    COUNTING_TIME_LIMIT_MAX,
    Source,
    cell_text,
    collect,
    counting_time_limit,
)

Batches = list[list[dict[str, Any]]]

_SLOW_SQL = (
    "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM c) "
    "SELECT x FROM c LIMIT 500000000"
)


class _Clock:
    """Controllable replacement for ``time.monotonic``."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> _Clock:
    """Patch the module clock with a manually advanced one."""
    fake = _Clock()
    monkeypatch.setattr("mcp_tools_sql.result_limits.time.monotonic", fake)
    return fake


def _rows(n: int, start: int = 0) -> list[dict[str, Any]]:
    return [{"id": i} for i in range(start, start + n)]


def _batched(rows: list[dict[str, Any]], size: int) -> Batches:
    return [rows[i : i + size] for i in range(0, len(rows), size)]


def _source(
    name: str,
    batches: Batches,
    *,
    error: Exception | None = None,
    before_error: Callable[[], None] | None = None,
    enforces_counting: bool = False,
    pulled: list[int] | None = None,
    opened: list[str] | None = None,
    closed: list[str] | None = None,
) -> Source:
    """Build a fake source yielding *batches*, then optionally raising."""

    def _open(counting: Deadline) -> Generator[list[dict[str, Any]], None, None]:
        assert isinstance(counting, Deadline)
        if opened is not None:
            opened.append(name)
        try:
            for batch in batches:
                if pulled is not None:
                    pulled.append(len(batch))
                yield batch
            if before_error is not None:
                before_error()
            if error is not None:
                raise error
        finally:
            if closed is not None:
                closed.append(name)

    return Source(name, _open, enforces_counting=enforces_counting)


def _limits(**kwargs: int) -> LimitsConfig:
    return LimitsConfig(**kwargs)


def _render(rows: list[dict[str, str]]) -> str:
    table: str = tabulate(
        rows, headers="keys", tablefmt="simple", disable_numparse=True
    )
    return table


class TestCellText:
    """``cell_text`` stringifies and cuts cells."""

    def test_none_is_empty(self) -> None:
        assert cell_text(None, 5) == ("", False)

    def test_short_value_unchanged(self) -> None:
        assert cell_text(12345, 5) == ("12345", False)

    def test_long_value_cut_with_marker(self) -> None:
        assert cell_text("x" * 1500, 10) == (
            "x" * 10 + "…[cut, 1,500 chars total]",
            True,
        )


class TestCountingTimeLimit:
    """``counting_time_limit`` is half the timeout, capped at 5 s."""

    def test_capped(self) -> None:
        assert counting_time_limit(30) == COUNTING_TIME_LIMIT_MAX == 5.0

    def test_half_of_short_timeout(self) -> None:
        assert counting_time_limit(4) == 2.0


class TestCounting:
    """Display rows and exact or bounded counts."""

    def test_exact_total_below_max_count(self) -> None:
        result = collect(
            [_source("db", _batched(_rows(250), 100))],
            max_rows=10,
            limits=_limits(max_count_rows=1000),
            counting_seconds=5.0,
        )
        assert result.total == 250
        assert result.complete is True
        assert result.stop == "end"
        assert result.rows == [{"id": str(i)} for i in range(10)]
        assert result.display_limit == "max_rows"
        assert result.sources[0].complete is True

    def test_reads_at_most_max_count_plus_one(self) -> None:
        pulled: list[int] = []
        closed: list[str] = []
        result = collect(
            [_source("db", _batched(_rows(1000), 1), pulled=pulled, closed=closed)],
            max_rows=5,
            limits=_limits(max_count_rows=100),
            counting_seconds=5.0,
        )
        assert sum(pulled) == 101
        assert closed == ["db"]
        assert result.total == 100
        assert result.complete is False
        assert result.stop == "max_count"
        assert len(result.rows) == 5
        assert result.sources[0].complete is False

    def test_no_truncation_when_everything_fits(self) -> None:
        result = collect(
            [_source("db", [_rows(3)])],
            max_rows=10,
            limits=_limits(),
            counting_seconds=5.0,
        )
        assert result.display_limit == ""
        assert result.total == 3
        assert len(result.rows) == 3

    def test_exactly_max_rows_is_not_a_display_limit(self) -> None:
        result = collect(
            [_source("db", [_rows(5)])],
            max_rows=5,
            limits=_limits(),
            counting_seconds=5.0,
        )
        assert result.display_limit == ""
        assert len(result.rows) == 5

    def test_filter_finds_matches_beyond_first_batch(self) -> None:
        result = collect(
            [_source("db", _batched(_rows(1000), 100))],
            max_rows=3,
            limits=_limits(),
            counting_seconds=5.0,
            filter_rows=lambda batch: [r for r in batch if r["id"] >= 500],
        )
        assert result.total == 500
        assert result.rows == [{"id": "500"}, {"id": "501"}, {"id": "502"}]

    def test_long_cells_cut_and_flagged(self) -> None:
        result = collect(
            [_source("db", [[{"v": "y" * 20}]])],
            max_rows=5,
            limits=_limits(max_cell_chars=4),
            counting_seconds=5.0,
        )
        assert result.cells_cut is True
        assert result.rows == [{"v": "yyyy…[cut, 20 chars total]"}]


class TestCountingTime:
    """The counting time limit runs from display completion."""

    def test_limit_passed_between_batches(self, clock: _Clock) -> None:
        def _advance() -> None:
            clock.now = 10.0

        batches = _batched(_rows(30), 10)

        def _open(_: Deadline) -> Generator[list[dict[str, Any]], None, None]:
            yield batches[0]
            _advance()
            yield batches[1]
            yield batches[2]

        result = collect(
            [Source("db", _open)],
            max_rows=2,
            limits=_limits(),
            counting_seconds=5.0,
        )
        assert result.stop == "counting"
        assert result.complete is False
        assert result.total == 20
        assert result.rows == [{"id": "0"}, {"id": "1"}]
        assert result.sources[0].complete is False

    def test_deadline_armed_at_display_completion(self, clock: _Clock) -> None:
        seen: list[float | None] = []

        def _open(counting: Deadline) -> Generator[list[dict[str, Any]], None, None]:
            seen.append(counting.at)
            clock.now = 3.0
            yield _rows(5)
            seen.append(counting.at)

        collect(
            [Source("db", _open)],
            max_rows=5,
            limits=_limits(),
            counting_seconds=2.0,
        )
        assert seen == [None, 5.0]


class TestTimeouts:
    """``QueryTimeoutError`` is caught inside the source loop."""

    @pytest.mark.parametrize(
        ("enforces", "expected"), [(True, "counting"), (False, "timeout")]
    )
    def test_timeout_after_counting_deadline(
        self, clock: _Clock, enforces: bool, expected: str
    ) -> None:
        def _advance() -> None:
            clock.now = 10.0

        result = collect(
            [
                _source(
                    "db",
                    [_rows(5)],
                    before_error=_advance,
                    error=QueryTimeoutError(30),
                    enforces_counting=enforces,
                )
            ],
            max_rows=2,
            limits=_limits(),
            counting_seconds=5.0,
        )
        assert result.stop == expected
        assert result.total == 5
        assert len(result.rows) == 2
        assert result.sources[0].complete is False
        assert result.sources[0].error == ""

    @pytest.mark.parametrize("enforces", [True, False])
    def test_timeout_before_counting_deadline(
        self, clock: _Clock, enforces: bool
    ) -> None:
        result = collect(
            [
                _source(
                    "db",
                    [_rows(5)],
                    error=QueryTimeoutError(30),
                    enforces_counting=enforces,
                )
            ],
            max_rows=2,
            limits=_limits(),
            counting_seconds=5.0,
        )
        assert clock.now == 0.0
        assert result.stop == "timeout"

    def test_timeout_during_display_keeps_rows(self, clock: _Clock) -> None:
        _ = clock
        result = collect(
            [_source("db", [_rows(3)], error=QueryTimeoutError(30))],
            max_rows=10,
            limits=_limits(),
            counting_seconds=5.0,
        )
        assert result.stop == "timeout"
        assert result.rows == [{"id": "0"}, {"id": "1"}, {"id": "2"}]
        assert result.total == 3
        assert result.sources[0].complete is False
        assert result.sources[0].timed_out is False
        assert result.sources[0].error == ""

    def test_timeout_before_any_row(self, clock: _Clock) -> None:
        _ = clock
        result = collect(
            [_source("db", [], error=QueryTimeoutError(30))],
            max_rows=10,
            limits=_limits(),
            counting_seconds=5.0,
        )
        assert result.stop == "timeout"
        assert result.rows == []
        src = result.sources[0]
        assert src.timed_out is True
        assert src.error == "Query aborted after 30 s (statement timeout)."
        assert src.complete is False


class TestFanOut:
    """Several sources share the display and counting budgets."""

    def test_shared_max_rows_and_exact_counts(self) -> None:
        result = collect(
            [
                _source("a", [_rows(3)]),
                _source("b", [_rows(4, start=100)]),
            ],
            max_rows=5,
            limits=_limits(),
            counting_seconds=5.0,
        )
        assert [r["id"] for r in result.rows] == ["0", "1", "2", "100", "101"]
        assert [(s.database, s.matched, s.complete) for s in result.sources] == [
            ("a", 3, True),
            ("b", 4, True),
        ]
        assert result.total == 7
        assert result.complete is True
        assert result.display_limit == "max_rows"

    def test_display_budget_exhausted_still_counts_second(self) -> None:
        result = collect(
            [
                _source("a", [_rows(20)]),
                _source("b", [_rows(7)]),
            ],
            max_rows=5,
            limits=_limits(),
            counting_seconds=5.0,
        )
        assert len(result.rows) == 5
        assert [s.matched for s in result.sources] == [20, 7]
        assert all(s.complete and s.queried for s in result.sources)

    def test_counting_budget_shared(self) -> None:
        result = collect(
            [
                _source("a", [_rows(60)]),
                _source("b", [_rows(60)]),
            ],
            max_rows=5,
            limits=_limits(max_count_rows=100),
            counting_seconds=5.0,
        )
        assert [(s.matched, s.complete) for s in result.sources] == [
            (60, True),
            (40, False),
        ]
        assert result.total == 100
        assert result.stop == "max_count"

    def test_second_not_queried_after_counting_budget(self) -> None:
        opened: list[str] = []
        result = collect(
            [
                _source("a", [_rows(150)], opened=opened),
                _source("b", [_rows(7)], opened=opened),
            ],
            max_rows=5,
            limits=_limits(max_count_rows=100),
            counting_seconds=5.0,
        )
        assert opened == ["a"]
        a, b = result.sources
        assert (a.matched, a.complete, a.queried) == (100, False, True)
        assert (b.database, b.matched, b.complete, b.queried) == ("b", 0, False, False)

    def test_error_recorded_and_counting_continues(self) -> None:
        closed: list[str] = []
        result = collect(
            [
                _source("a", [_rows(2)], error=RuntimeError("boom"), closed=closed),
                _source("b", [_rows(3)], closed=closed),
            ],
            max_rows=10,
            limits=_limits(),
            counting_seconds=5.0,
            record_errors=True,
        )
        assert closed == ["a", "b"]
        assert result.sources[0].error == "boom"
        assert result.sources[1].matched == 3
        assert result.stop == "end"
        assert len(result.rows) == 3

    def test_error_mid_count_drops_partial_count(self) -> None:
        result = collect(
            [
                _source("a", [_rows(2), _rows(3)], error=RuntimeError("boom")),
                _source("b", [_rows(4)]),
            ],
            max_rows=1,
            limits=_limits(),
            counting_seconds=5.0,
            record_errors=True,
        )
        a, b = result.sources
        assert (a.error, a.matched) == ("boom", 0)
        assert (b.matched, b.complete) == (4, True)
        assert result.total == 4
        out = render_limited(
            result,
            max_rows=1,
            max_rows_hard=100,
            has_sql_params=False,
            filter_column="",
            builtin=True,
            fanout=True,
            max_output_chars=80_000,
            max_cell_chars=500,
        )
        assert "of 4 rows" in out
        assert "Matched: b 4." in out

    def test_error_drops_display_rows_of_failed_database(self) -> None:
        result = collect(
            [
                _source("a", [_rows(80)], error=RuntimeError("boom")),
                _source("b", [_rows(30, start=100)]),
            ],
            max_rows=50,
            limits=_limits(),
            counting_seconds=5.0,
            record_errors=True,
        )
        assert [r["id"] for r in result.rows] == [str(i) for i in range(100, 130)]
        assert result.total == 30
        assert result.complete is True
        assert result.display_limit == ""
        out = render_limited(
            result,
            max_rows=50,
            max_rows_hard=100,
            has_sql_params=False,
            filter_column="",
            builtin=True,
            fanout=True,
            max_output_chars=80_000,
            max_cell_chars=500,
        )
        assert "Output truncated" not in out
        assert "a: boom" in out

    def test_max_count_on_first_row_of_next_database_is_not_queried(self) -> None:
        result = collect(
            [
                _source("a", [_rows(100)]),
                _source("b", [_rows(7)]),
            ],
            max_rows=5,
            limits=_limits(max_count_rows=100),
            counting_seconds=5.0,
        )
        assert result.stop == "max_count"
        b = result.sources[1]
        assert (b.matched, b.queried) == (0, False)
        out = render_limited(
            result,
            max_rows=5,
            max_rows_hard=100,
            has_sql_params=False,
            filter_column="",
            builtin=True,
            fanout=True,
            max_output_chars=80_000,
            max_cell_chars=500,
        )
        assert "Matched: a 100, b not queried (limit reached)." in out
        assert "b 0+" not in out

    def test_counting_deadline_before_any_match_is_not_queried(
        self, clock: _Clock
    ) -> None:
        def _advance() -> None:
            clock.now = 10.0

        result = collect(
            [
                _source("a", [_rows(5)], enforces_counting=True),
                _source(
                    "b",
                    [],
                    before_error=_advance,
                    error=QueryTimeoutError(30),
                    enforces_counting=True,
                ),
            ],
            max_rows=2,
            limits=_limits(),
            counting_seconds=5.0,
            record_errors=True,
        )
        assert result.stop == "counting"
        b = result.sources[1]
        assert (b.queried, b.error, b.timed_out) == (False, "", False)
        out = render_limited(
            result,
            max_rows=2,
            max_rows_hard=100,
            has_sql_params=False,
            filter_column="",
            builtin=True,
            fanout=True,
            max_output_chars=80_000,
            max_cell_chars=500,
        )
        assert "Matched: a 5, b not queried (limit reached)." in out
        assert "b 0+" not in out

    def test_error_reraised_without_record_errors(self) -> None:
        closed: list[str] = []
        with pytest.raises(RuntimeError, match="boom"):
            collect(
                [_source("a", [], error=RuntimeError("boom"), closed=closed)],
                max_rows=10,
                limits=_limits(),
                counting_seconds=5.0,
            )
        assert closed == ["a"]


class TestCharBudget:
    """Display rows fit the rendered ``max_output_chars`` budget."""

    @staticmethod
    def _check(batch: list[dict[str, Any]], budgets: range) -> None:
        for budget in budgets:
            result = collect(
                [_source("db", [batch])],
                max_rows=100,
                limits=_limits(max_output_chars=budget),
                counting_seconds=5.0,
            )
            assert result.total == len(batch)
            if result.rows:
                assert len(_render(result.rows)) <= budget
            if len(result.rows) < len(batch):
                assert result.display_limit == "chars"

    def test_later_row_widens_earlier_column(self) -> None:
        batch: list[dict[str, Any]] = [
            {"a": "x", "b": "y" * 10, "c": "z"},
            {"a": "x" * 30, "b": "y", "c": "z"},
            {"a": "x" * 5, "b": "y" * 40, "c": "z" * 3},
            {"a": "x" * 60, "b": "y", "c": "z"},
        ]
        self._check(batch, range(20, 600, 3))

    def test_multiline_cells(self) -> None:
        batch: list[dict[str, Any]] = [
            {"a": "one", "b": "x"},
            {"a": "two\nlines", "b": "y" * 15},
            {"a": "three\nmore\nlines\r\nhere", "b": "z"},
            {"a": "w", "b": "v\nv"},
        ]
        self._check(batch, range(20, 400, 3))

    def test_header_wider_than_cells(self) -> None:
        batch: list[dict[str, Any]] = [
            {"a_very_long_column_header_name": 1, "b": 2} for _ in range(10)
        ]
        self._check(batch, range(20, 600, 3))

    def test_first_row_too_wide(self) -> None:
        result = collect(
            [_source("db", [[{"a": "x" * 50}, {"a": "y"}]])],
            max_rows=10,
            limits=_limits(max_output_chars=10),
            counting_seconds=5.0,
        )
        assert result.rows == []
        assert result.display_limit == "chars"
        assert result.total == 2

    def test_chars_refusal_stops_display(self) -> None:
        result = collect(
            [_source("db", [[{"a": "x"}, {"a": "y" * 500}, {"a": "z"}]])],
            max_rows=10,
            limits=_limits(max_output_chars=100),
            counting_seconds=5.0,
        )
        assert result.rows == [{"a": "x"}]
        assert result.display_limit == "chars"
        assert result.total == 3


@pytest.mark.sqlite_integration
class TestSQLiteCounting:
    """The counting deadline cuts a real SQLite read short."""

    @staticmethod
    def _backend(tmp_path: Path) -> SQLiteBackend:
        return SQLiteBackend(
            ConnectionConfig(
                backend="sqlite",
                path=str(tmp_path / "c.db"),
                query_timeout_seconds=2,
            )
        )

    def test_counting_cut_mid_batch(self, tmp_path: Path) -> None:
        backend = self._backend(tmp_path)
        source = Source(
            "db",
            lambda counting: backend.iter_readonly_batches(
                _SLOW_SQL, counting=counting
            ),
            enforces_counting=True,
        )
        start = time.monotonic()
        result = collect(
            [source],
            max_rows=5,
            limits=_limits(max_count_rows=1_000_000_000),
            counting_seconds=counting_time_limit(2),
        )
        assert time.monotonic() - start < 2
        assert result.stop == "counting"
        assert len(result.rows) == 5
        assert result.complete is False

    def test_selective_filter_counting_not_timeout(self, tmp_path: Path) -> None:
        backend = self._backend(tmp_path)
        max_rows = 5
        source = Source(
            "db",
            lambda counting: backend.iter_readonly_batches(
                _SLOW_SQL, counting=counting
            ),
            enforces_counting=True,
        )
        start = time.monotonic()
        result = collect(
            [source],
            max_rows=max_rows,
            limits=_limits(),
            counting_seconds=counting_time_limit(2),
            filter_rows=lambda batch: [
                r for r in batch if r["x"] <= max_rows or r["x"] == 10**9
            ],
        )
        assert time.monotonic() - start < 2
        assert result.stop == "counting"
        assert result.rows == [{"x": str(i)} for i in range(1, max_rows + 1)]
        assert result.total == max_rows
