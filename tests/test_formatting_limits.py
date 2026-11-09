"""Tests for ``render_limited``: truncation messages and rendering."""

from __future__ import annotations

from typing import Any

import pytest

from mcp_tools_sql.formatting import LimitedResult, SourceCount, render_limited


def _rows(n: int) -> list[dict[str, str]]:
    return [{"id": str(i)} for i in range(n)]


def _render(result: LimitedResult, **overrides: Any) -> str:
    kwargs: dict[str, Any] = {
        "max_rows": 100,
        "max_rows_hard": 500,
        "has_sql_params": False,
        "filter_column": "",
        "builtin": False,
        "fanout": False,
        "max_output_chars": 80000,
        "max_cell_chars": 500,
    }
    kwargs.update(overrides)
    return render_limited(result, **kwargs)


def _single(
    shown: int,
    matched: int,
    *,
    display_limit: Any = "",
    stop: Any = "end",
    cells_cut: bool = False,
) -> LimitedResult:
    return LimitedResult(
        rows=_rows(shown),
        sources=[SourceCount("db", matched=matched, complete=stop == "end")],
        display_limit=display_limit,
        stop=stop,
        cells_cut=cells_cut,
    )


class TestTable:
    """Table rendering without truncation."""

    def test_no_rows(self) -> None:
        assert _render(_single(0, 0)) == "No results found."

    def test_complete_has_no_message(self) -> None:
        out = _render(_single(3, 3))
        assert "Output truncated" not in out
        assert out.splitlines()[0].strip() == "id"

    def test_numbers_are_not_parsed(self) -> None:
        result = LimitedResult(
            rows=[{"v": "1.5"}, {"v": "10"}], sources=[SourceCount("db", 2)]
        )
        lines = _render(result).splitlines()
        assert lines[2] == "1.5"
        assert lines[3] == "10"


class TestMaxRows:
    """``max_rows`` reached."""

    def test_exact_total_with_params(self) -> None:
        out = _render(_single(100, 4213, display_limit="max_rows"), has_sql_params=True)
        assert (
            "[Output truncated: showing 100 of 4,213 rows (max_rows=100 reached)."
            in out
        )
        assert (
            "To see more rows: increase max_rows (hard limit 500) or refine parameters.]"
            in out
        )

    def test_at_hard_limit_only_params(self) -> None:
        out = _render(
            _single(500, 4213, display_limit="max_rows"),
            max_rows=500,
            has_sql_params=True,
        )
        assert "To see more rows: refine parameters.]" in out
        assert "increase max_rows" not in out

    def test_builtin_no_next_step(self) -> None:
        out = _render(
            _single(100, 4213, display_limit="max_rows"),
            max_rows=100,
            max_rows_hard=100,
            builtin=True,
        )
        assert out.endswith(
            "[Output truncated: showing 100 of 4,213 rows (max_rows=100 reached).]"
        )
        assert "max_rows_hard" not in out
        assert "To see" not in out

    def test_configured_at_hard_limit_operator(self) -> None:
        out = _render(
            _single(100, 4213, display_limit="max_rows"),
            max_rows=100,
            max_rows_hard=100,
        )
        assert "\nOperator: raise max_rows_hard in the query config.]" in out

    def test_filter_column(self) -> None:
        out = _render(
            _single(100, 4213, display_limit="max_rows"),
            max_rows=100,
            max_rows_hard=100,
            filter_column="name",
            builtin=True,
        )
        assert "To see more rows: narrow with name_filter.]" in out
        assert "parameters" not in out

    def test_counting_stopped(self) -> None:
        out = _render(_single(100, 37000, display_limit="max_rows", stop="max_count"))
        assert (
            "showing 100 of 37,000+ rows (max_rows=100 reached; counting stopped)."
            in out
        )

    def test_counting_time_limit(self) -> None:
        out = _render(_single(100, 900, display_limit="max_rows", stop="counting"))
        assert (
            "showing 100 of 900+ rows (max_rows=100 reached; counting stopped)." in out
        )


class TestChars:
    """Output char budget reached."""

    def test_with_params(self) -> None:
        out = _render(_single(40, 4213, display_limit="chars"), has_sql_params=True)
        assert "showing 40 of 4,213 rows (80,000-char output limit reached)." in out
        assert "To see different or fewer rows: filter with parameters.]" in out

    def test_with_filter(self) -> None:
        out = _render(_single(40, 4213, display_limit="chars"), filter_column="name")
        assert "To see different or fewer rows: narrow with name_filter.]" in out

    def test_without_params_or_filter(self) -> None:
        out = _render(_single(40, 4213, display_limit="chars"))
        assert "\nOperator: raise [limits] max_output_chars.]" in out

    @pytest.mark.parametrize(
        ("builtin", "operator"),
        [
            (
                False,
                "Operator: select fewer columns in the configured SQL or raise "
                "[limits] max_output_chars.",
            ),
            (True, "Operator: raise [limits] max_output_chars."),
        ],
    )
    def test_first_row_too_wide(self, builtin: bool, operator: str) -> None:
        out = _render(
            _single(0, 12, display_limit="chars"),
            builtin=builtin,
            has_sql_params=True,
        )
        assert out == (
            "No results found.\n\n[Output truncated: the first row is wider than "
            "the 80,000-char output limit; showing 0 of 12 rows.\n" + operator + "]"
        )


class TestTimeout:
    """Statement timeout."""

    @pytest.mark.parametrize(("has_params", "hint"), [(False, False), (True, True)])
    def test_after_rows(self, has_params: bool, hint: bool) -> None:
        out = _render(_single(5, 5, stop="timeout"), has_sql_params=has_params)
        assert "showing 5 of 5+ rows (stopped: statement timeout)." in out
        assert ("Use more selective parameters." in out) is hint

    def test_before_any_row_no_params(self) -> None:
        result = LimitedResult(
            rows=[],
            sources=[
                SourceCount(
                    "db",
                    complete=False,
                    error="Query aborted after 30 s (statement timeout).",
                    timed_out=True,
                )
            ],
            stop="timeout",
        )
        assert _render(result) == "Query aborted after 30 s (statement timeout)."
        assert _render(result, has_sql_params=True) == (
            "Query aborted after 30 s (statement timeout). "
            "Use more selective parameters."
        )


def test_cells_cut_line() -> None:
    out = _render(_single(3, 3, cells_cut=True))
    assert out.endswith("\n\nLong values were cut at 500 chars.")


class TestFanout:
    """Fan-out footer and error lines."""

    def test_footer_counts(self) -> None:
        result = LimitedResult(
            rows=_rows(100),
            sources=[
                SourceCount("sales", matched=4213),
                SourceCount("hr", matched=37000, complete=False),
                SourceCount("fin", complete=False, queried=False),
            ],
            display_limit="max_rows",
            stop="max_count",
        )
        out = _render(result, fanout=True)
        assert (
            "\n\nMatched: sales 4,213, hr 37,000+, fin not queried (limit reached)."
            in out
        )

    def test_footer_timeout_not_queried(self) -> None:
        result = LimitedResult(
            rows=_rows(5),
            sources=[
                SourceCount("sales", matched=5, complete=False),
                SourceCount("fin", complete=False, queried=False),
            ],
            stop="timeout",
        )
        out = _render(result, fanout=True)
        assert "Matched: sales 5+, fin not queried (stopped: statement timeout)." in out

    def test_error_lines(self) -> None:
        result = LimitedResult(
            rows=_rows(100),
            sources=[
                SourceCount("sales", matched=150),
                SourceCount("hr", error="boom"),
            ],
            display_limit="max_rows",
        )
        out = _render(result, fanout=True)
        assert "Matched: sales 150." in out
        assert out.endswith("\n\nhr: boom")

    def test_no_footer_when_complete(self) -> None:
        result = LimitedResult(
            rows=_rows(5),
            sources=[SourceCount("sales", matched=2), SourceCount("hr", matched=3)],
        )
        out = _render(result, fanout=True)
        assert "Matched" not in out
        assert "Output truncated" not in out

    def test_no_footer_single_target(self) -> None:
        out = _render(_single(100, 4213, display_limit="max_rows"))
        assert "Matched" not in out
