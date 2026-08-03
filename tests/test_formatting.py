"""Tests for format_rows() output formatting."""

from __future__ import annotations

from mcp_tools_sql.formatting import (
    format_fanout_rows,
    format_rows,
    format_update_result,
)


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

    def test_truncation_hint_default_is_empty(self) -> None:
        """Default ``truncation_hint`` produces no schema-specific suffix."""
        rows = [{"id": i} for i in range(20)]
        result = format_rows(rows, max_rows=5)
        last_line = result.strip().split("\n")[-1]
        assert last_line.endswith("rows.")
        assert "Use filter to narrow" not in result

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

    def test_truncation_with_custom_hint(self) -> None:
        """Custom truncation_hint replaces the default suffix."""
        rows = [{"id": i} for i in range(20)]
        result = format_rows(rows, max_rows=5, truncation_hint="Refine query.")
        assert "Showing 5 of 20 rows" in result
        assert "Refine query." in result
        assert "Use filter to narrow" not in result

    def test_truncation_with_empty_hint(self) -> None:
        """Empty truncation_hint produces only the count line."""
        rows = [{"id": i} for i in range(20)]
        result = format_rows(rows, max_rows=5, truncation_hint="")
        assert "Showing 5 of 20 rows." in result
        last_line = result.strip().split("\n")[-1]
        assert last_line.endswith("rows.")
        assert "Use filter to narrow" not in result


class TestFormatFanoutRows:
    """Tests for the format_fanout_rows function."""

    def test_single_db_no_errors_equals_format_rows(self) -> None:
        """One database, no errors → byte-identical to format_rows output."""
        rows = [
            {"name": "alice", "_database": "sales"},
            {"name": "bob", "_database": "sales"},
        ]
        counts = {"sales": 2}
        result = format_fanout_rows(rows, counts, [], max_rows=100)
        assert result == format_rows(rows, 100)

    def test_single_db_no_errors_passes_hint_through(self) -> None:
        """Delegation preserves the truncation hint for the single-db case."""
        rows = [{"id": i, "_database": "sales"} for i in range(20)]
        counts = {"sales": 20}
        result = format_fanout_rows(
            rows, counts, [], max_rows=5, truncation_hint="Refine query."
        )
        assert result == format_rows(rows, 5, truncation_hint="Refine query.")

    def test_two_dbs_no_truncation_shows_all_without_footer(self) -> None:
        """Two databases below the cap render the merged table with no footer."""
        rows = [
            {"name": "alice", "_database": "sales"},
            {"name": "carol", "_database": "hr"},
        ]
        counts = {"sales": 1, "hr": 1}
        result = format_fanout_rows(rows, counts, [], max_rows=100)
        assert "alice" in result
        assert "carol" in result
        assert "_database" in result
        assert "Showing" not in result
        assert "Matched:" not in result

    def test_two_dbs_truncation_shows_exact_per_db_footer(self) -> None:
        """On truncation the footer lists exact per-database counts."""
        rows = [{"id": i, "_database": "sales"} for i in range(3)] + [
            {"id": i, "_database": "hr"} for i in range(4)
        ]
        counts = {"sales": 3, "hr": 4}
        result = format_fanout_rows(rows, counts, [], max_rows=5)
        assert "Showing 5 of 7 rows." in result
        assert "Matched: sales 3, hr 4." in result

    def test_footer_only_on_truncation(self) -> None:
        """Exactly max_rows merged rows → no footer even with multiple dbs."""
        rows = [{"id": 1, "_database": "sales"}, {"id": 2, "_database": "hr"}]
        counts = {"sales": 1, "hr": 1}
        result = format_fanout_rows(rows, counts, [], max_rows=2)
        assert "Showing" not in result
        assert "Matched:" not in result

    def test_errors_rendered_inline(self) -> None:
        """A failed database is rendered inline; other rows still shown."""
        rows = [{"name": "alice", "_database": "sales"}]
        counts = {"sales": 1}
        errors = [("hr", "connection refused")]
        result = format_fanout_rows(rows, counts, errors, max_rows=100)
        assert "alice" in result
        assert "hr: connection refused" in result

    def test_errors_only_no_rows(self) -> None:
        """All databases failing renders no table body but lists every error."""
        errors = [("sales", "boom"), ("hr", "kaboom")]
        result = format_fanout_rows([], {}, errors, max_rows=100)
        assert "No results found." in result
        assert "sales: boom" in result
        assert "hr: kaboom" in result

    def test_truncation_footer_hint_appended(self) -> None:
        """The truncation hint is appended after the per-db footer breakdown."""
        rows = [{"id": i, "_database": "sales"} for i in range(3)] + [
            {"id": i, "_database": "hr"} for i in range(3)
        ]
        counts = {"sales": 3, "hr": 3}
        result = format_fanout_rows(
            rows, counts, [], max_rows=4, truncation_hint="Use filter to narrow."
        )
        assert "Matched: sales 3, hr 3. Use filter to narrow." in result


class TestFormatUpdateResult:
    """Tests for the format_update_result function."""

    def test_zero_rows_returns_no_row_found_text(self) -> None:
        """Zero affected rows produces a 'No row found' message."""
        result = format_update_result(0, "customers", "id", 42)
        assert "No row found" in result
        assert "customers" in result
        assert "42" in result
        assert "WARNING:" not in result

    def test_one_row_success_message(self) -> None:
        """One affected row produces a success confirmation."""
        result = format_update_result(1, "customers", "id", 42)
        assert "1 row" in result
        assert "customers" in result
        assert "42" in result
        assert "WARNING:" not in result

    def test_multiple_rows_starts_with_warning_token(self) -> None:
        """More than one affected row starts with WARNING: on its own line."""
        result = format_update_result(3, "customers", "id", 42)
        first_line = result.splitlines()[0]
        assert first_line.startswith("WARNING:")
        assert "3" in result
        assert "customers" in result

    def test_qualified_table_with_schema(self) -> None:
        """A schema-qualified table name appears verbatim in the output."""
        result = format_update_result(1, "dbo.customers", "id", 7)
        assert "dbo.customers" in result

    def test_qualified_table_without_schema(self) -> None:
        """An unqualified table name appears verbatim in the output."""
        result = format_update_result(1, "customers", "id", 7)
        assert "customers" in result
        assert "dbo." not in result
