"""Tests for the sql_placeholders module."""

from __future__ import annotations

from mcp_tools_sql.utils.sql_placeholders import (
    extract_param_names,
    translate_named_to_qmark,
)


class TestExtractParamNames:
    """Tests for ``extract_param_names``."""

    def test_basic(self) -> None:
        assert extract_param_names("SELECT :a AND :b") == {"a", "b"}

    def test_inside_single_quotes(self) -> None:
        assert extract_param_names("SELECT * FROM t WHERE x = ':a'") == set()

    def test_inside_double_quotes(self) -> None:
        assert extract_param_names('SELECT * FROM t WHERE "x:a" = 1') == set()

    def test_inside_line_comment(self) -> None:
        assert extract_param_names("SELECT 1 -- :a") == set()

    def test_inside_block_comment(self) -> None:
        assert extract_param_names("SELECT 1 /* :a */") == set()

    def test_repeated_name(self) -> None:
        assert extract_param_names("SELECT :a + :a") == {"a"}

    def test_multi_statement(self) -> None:
        assert extract_param_names("SELECT :a; SELECT :b") == {"a", "b"}

    def test_no_placeholders(self) -> None:
        assert extract_param_names("SELECT 1") == set()


class TestTranslateNamedToQmark:
    """Tests for ``translate_named_to_qmark``."""

    def test_basic(self) -> None:
        assert translate_named_to_qmark("SELECT :a, :b") == (
            "SELECT ?, ?",
            ["a", "b"],
        )

    def test_repeated_name(self) -> None:
        assert translate_named_to_qmark("WHERE x = :a OR y = :a") == (
            "WHERE x = ? OR y = ?",
            ["a", "a"],
        )

    def test_inside_string_untouched(self) -> None:
        assert translate_named_to_qmark("SELECT ':a' WHERE x = :b") == (
            "SELECT ':a' WHERE x = ?",
            ["b"],
        )

    def test_inside_comment_untouched(self) -> None:
        sql_out, names = translate_named_to_qmark("SELECT :a -- :b\nFROM t")
        assert sql_out == "SELECT ? -- :b\nFROM t"
        assert names == ["a"]

    def test_no_placeholders(self) -> None:
        sql = "SELECT 1 FROM dual"
        assert translate_named_to_qmark(sql) == (sql, [])

    def test_translate_preserves_separator_in_multistatement(self) -> None:
        sql_out, names = translate_named_to_qmark("SELECT :a; SELECT :b")
        assert sql_out == "SELECT ?; SELECT ?"
        assert names == ["a", "b"]
