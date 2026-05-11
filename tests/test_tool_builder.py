"""Tests for tool_builder helper functions."""

from __future__ import annotations

from mcp_tools_sql.tool_builder import apply_filter, extract_sql_params


class TestExtractSqlParams:
    """Tests for extract_sql_params."""

    def test_single_param(self) -> None:
        assert extract_sql_params("SELECT * WHERE x = :id") == {"id"}

    def test_multiple_params(self) -> None:
        assert extract_sql_params("WHERE a = :x AND b = :y") == {"x", "y"}

    def test_no_params(self) -> None:
        assert extract_sql_params("SELECT 'main' AS name") == set()

    def test_duplicate_param(self) -> None:
        assert extract_sql_params("WHERE a = :x OR b = :x") == {"x"}


class TestApplyFilter:
    """Tests for apply_filter."""

    def test_no_filter(self) -> None:
        """None filter returns all rows."""
        rows = [{"name": "a"}, {"name": "b"}]
        assert apply_filter(rows, "name", None) == rows

    def test_glob_match(self) -> None:
        """Glob pattern filters rows by the given column."""
        rows = [
            {"name": "user_id"},
            {"name": "user_name"},
            {"name": "order_id"},
        ]
        result = apply_filter(rows, "name", "user_*")
        assert result == [{"name": "user_id"}, {"name": "user_name"}]

    def test_case_insensitive(self) -> None:
        """Filter is case-insensitive."""
        rows = [{"name": "User_ID"}, {"name": "order_id"}]
        result = apply_filter(rows, "name", "user_*")
        assert result == [{"name": "User_ID"}]

    def test_no_match(self) -> None:
        """No matching rows returns empty list."""
        rows = [{"name": "a"}, {"name": "b"}]
        assert apply_filter(rows, "name", "z*") == []
