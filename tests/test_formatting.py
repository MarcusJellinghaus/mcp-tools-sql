"""Tests for format_rows() output formatting."""

from __future__ import annotations

from mcp_tools_sql.formatting import format_rows


class TestFormatRows:
    """Tests for the format_rows function."""

    def test_basic_table(self) -> None:
        """Formats rows as tabular text with column headers."""
        rows = [
            {"name": "alice", "age": 30},
            {"name": "bob", "age": 25},
        ]
        result = format_rows(rows)
        assert "name" in result
        assert "age" in result
        assert "alice" in result
        assert "bob" in result
        assert "30" in result
        assert "25" in result

    def test_empty_rows(self) -> None:
        """Returns 'No results found.' for empty list."""
        assert format_rows([]) == "No results found."

    def test_single_row(self) -> None:
        """Single row formats correctly."""
        rows = [{"id": 1, "value": "test"}]
        result = format_rows(rows)
        assert "id" in result
        assert "value" in result
        assert "1" in result
        assert "test" in result

    def test_truncation_at_max_rows(self) -> None:
        """Rows beyond max_rows are truncated with warning message."""
        rows = [{"id": i} for i in range(10)]
        result = format_rows(rows, max_rows=5)
        # Should only show first 5 rows
        for i in range(5):
            assert str(i) in result
        # Row 9 should not appear in the table data
        lines = result.strip().split("\n")
        # The table lines (excluding header, separator, and warning) should be 5
        table_lines = [
            line
            for line in lines
            if line.strip()
            and not line.startswith("-")
            and "id" not in line.lower()
            and "Showing" not in line
        ]
        assert len(table_lines) == 5

    def test_truncation_message_text(self) -> None:
        """Warning includes actual count and max_rows."""
        rows = [{"id": i} for i in range(20)]
        result = format_rows(rows, max_rows=5)
        assert "Showing 5 of 20 rows" in result
        assert "Use filter to narrow" in result

    def test_no_truncation_at_boundary(self) -> None:
        """Exactly max_rows rows → no truncation message."""
        rows = [{"id": i} for i in range(5)]
        result = format_rows(rows, max_rows=5)
        assert "Showing" not in result

    def test_column_headers_from_dict_keys(self) -> None:
        """Column headers come from dict keys of first row."""
        rows = [{"col_a": 1, "col_b": "x"}]
        result = format_rows(rows)
        assert "col_a" in result
        assert "col_b" in result
