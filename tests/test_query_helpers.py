"""Tests for the query_helpers module."""

from __future__ import annotations

from typing import Any

import pytest

from mcp_tools_sql.config.models import QueryConfig
from mcp_tools_sql.query_helpers import (
    _cap_max_rows,
    execute_and_format,
    extract_sql_params,
)


def test_extract_sql_params_skips_string_literal() -> None:
    """Delegation guarantee: placeholders inside string literals are ignored."""
    assert extract_sql_params("SELECT ':foo' AS x WHERE id = :bar") == {"bar"}


@pytest.mark.asyncio
async def test_execute_and_format_caps_max_rows_and_filters() -> None:
    """execute_and_format clamps max_rows (with note) and applies the filter."""

    class _StubBackend:
        def execute_query(
            self, sql: str, params: dict[str, Any] | None = None
        ) -> list[dict[str, Any]]:
            return [{"name": "Bank A"}, {"name": "Bank B"}, {"name": "Bank C"}]

        def execute_readonly_query(
            self, sql: str, params: dict[str, Any] | None = None
        ) -> list[dict[str, Any]]:
            return self.execute_query(sql, params)

    config = QueryConfig(
        description="",
        sql="SELECT name FROM customers",
        max_rows_default=5,
        max_rows_hard=10,
        filter_column="name",
    )

    text = await execute_and_format(
        "customers",
        "SELECT name FROM customers",
        set(),
        _StubBackend(),  # type: ignore[arg-type]
        config,
        "name_filter",
        "hint",
        {"max_rows": 500, "name_filter": "Bank A"},
    )

    assert "Requested max_rows=500 exceeds hard limit 10" in text
    assert "capped at 10" in text
    assert "Bank A" in text
    assert "Bank B" not in text


class _ThreeRowBackend:
    """A stub backend returning three named rows on every query."""

    def execute_query(
        self, sql: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Return three fixed rows.

        Returns:
            Three single-column rows, enough to observe any row cap.
        """
        return [{"name": "Bank A"}, {"name": "Bank B"}, {"name": "Bank C"}]

    def execute_readonly_query(
        self, sql: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Return the same three rows through the read-only path.

        Returns:
            Three single-column rows, enough to observe any row cap.
        """
        return self.execute_query(sql, params)


async def _run_execute_and_format(config: QueryConfig, kwargs: dict[str, Any]) -> str:
    """Run ``execute_and_format`` over ``_ThreeRowBackend`` with ``kwargs``.

    Returns:
        The rendered result text, including any appended max_rows note.
    """
    return await execute_and_format(
        "customers",
        "SELECT name FROM customers",
        set(),
        _ThreeRowBackend(),  # type: ignore[arg-type]
        config,
        None,
        "hint",
        kwargs,
    )


@pytest.mark.asyncio
async def test_execute_and_format_below_minimum_max_rows_notes_and_caps() -> None:
    """A below-minimum max_rows renders one row and says so in the output."""
    config = QueryConfig(sql="SELECT name FROM customers", max_rows_hard=10)

    text = await _run_execute_and_format(config, {"max_rows": -1})

    assert "Requested max_rows=-1 is below the minimum 1; using 1." in text
    assert "Showing 1 of 3 rows." in text
    assert "Bank B" not in text


@pytest.mark.asyncio
async def test_execute_and_format_omitted_max_rows_uses_floored_default() -> None:
    """An omitted max_rows with a non-positive default caps silently at 1."""
    config = QueryConfig(
        sql="SELECT name FROM customers", max_rows_default=0, max_rows_hard=0
    )

    text = await _run_execute_and_format(config, {})

    assert "below the minimum" not in text
    assert "Showing 1 of 3 rows." in text
    assert "Bank B" not in text


def test_cap_max_rows_floors_both_operands() -> None:
    """Negative/zero requested and a non-positive hard limit both floor to 1."""
    cfg = QueryConfig(sql="SELECT 1", max_rows_default=5, max_rows_hard=10)
    assert _cap_max_rows(cfg, -1)[0] == 1
    assert "below the minimum 1" in _cap_max_rows(cfg, -1)[1]
    assert _cap_max_rows(cfg, 0)[0] == 1
    assert _cap_max_rows(cfg, 3) == (3, "")

    bad_hard = QueryConfig(sql="SELECT 1", max_rows_default=5, max_rows_hard=-1)
    capped, note = _cap_max_rows(bad_hard, 5)
    assert capped == 1
    assert "capped at 1" in note
