"""Tests for schema_tools helper functions."""

from __future__ import annotations

from mcp_tools_sql.schema_tools import _apply_filter, _extract_sql_params


class TestExtractSqlParams:
    """Tests for _extract_sql_params."""

    def test_single_param(self) -> None:
        assert _extract_sql_params("SELECT * WHERE x = :id") == {"id"}

    def test_multiple_params(self) -> None:
        assert _extract_sql_params("WHERE a = :x AND b = :y") == {"x", "y"}

    def test_no_params(self) -> None:
        assert _extract_sql_params("SELECT 'main' AS name") == set()

    def test_duplicate_param(self) -> None:
        assert _extract_sql_params("WHERE a = :x OR b = :x") == {"x"}


class TestApplyFilter:
    """Tests for _apply_filter."""

    def test_no_filter(self) -> None:
        """None filter returns all rows."""
        rows = [{"name": "a"}, {"name": "b"}]
        assert _apply_filter(rows, None) == rows

    def test_glob_match(self) -> None:
        """Glob pattern filters rows by 'name' field."""
        rows = [
            {"name": "user_id"},
            {"name": "user_name"},
            {"name": "order_id"},
        ]
        result = _apply_filter(rows, "user_*")
        assert result == [{"name": "user_id"}, {"name": "user_name"}]

    def test_case_insensitive(self) -> None:
        """Filter is case-insensitive."""
        rows = [{"name": "User_ID"}, {"name": "order_id"}]
        result = _apply_filter(rows, "user_*")
        assert result == [{"name": "User_ID"}]

    def test_no_match(self) -> None:
        """No matching rows returns empty list."""
        rows = [{"name": "a"}, {"name": "b"}]
        assert _apply_filter(rows, "z*") == []
