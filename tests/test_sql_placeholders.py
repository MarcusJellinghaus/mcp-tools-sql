"""Tests for the sql_placeholders module."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

from mcp_tools_sql.utils.sql_placeholders import (
    extract_param_names,
    substitute_named_with_literals,
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


class TestSubstituteNamedWithLiterals:
    """Tests for ``substitute_named_with_literals``."""

    def test_int(self) -> None:
        assert substitute_named_with_literals("SELECT :a", {"a": 1}) == "SELECT 1"

    def test_negative_int(self) -> None:
        assert substitute_named_with_literals("SELECT :a", {"a": -7}) == "SELECT -7"

    def test_float(self) -> None:
        assert substitute_named_with_literals("SELECT :a", {"a": 1.5}) == "SELECT 1.5"

    def test_float_nan_raises(self) -> None:
        with pytest.raises(ValueError, match="non-finite"):
            substitute_named_with_literals("SELECT :a", {"a": float("nan")})

    def test_float_inf_raises(self) -> None:
        with pytest.raises(ValueError, match="non-finite"):
            substitute_named_with_literals("SELECT :a", {"a": float("inf")})

    def test_float_neg_inf_raises(self) -> None:
        with pytest.raises(ValueError, match="non-finite"):
            substitute_named_with_literals("SELECT :a", {"a": float("-inf")})

    def test_bool_true_renders_as_one(self) -> None:
        # bool must NOT be rendered through the int branch.
        assert substitute_named_with_literals("SELECT :a", {"a": True}) == "SELECT 1"

    def test_bool_false_renders_as_zero(self) -> None:
        assert substitute_named_with_literals("SELECT :a", {"a": False}) == "SELECT 0"

    def test_str_simple(self) -> None:
        assert (
            substitute_named_with_literals("SELECT :a", {"a": "hello"})
            == "SELECT 'hello'"
        )

    def test_str_with_single_quote_escaped(self) -> None:
        assert (
            substitute_named_with_literals("SELECT :a", {"a": "O'Reilly"})
            == "SELECT 'O''Reilly'"
        )

    def test_none_renders_null(self) -> None:
        assert substitute_named_with_literals("SELECT :a", {"a": None}) == "SELECT NULL"

    def test_date(self) -> None:
        assert (
            substitute_named_with_literals("SELECT :a", {"a": dt.date(2024, 1, 2)})
            == "SELECT '2024-01-02'"
        )

    def test_datetime(self) -> None:
        value = dt.datetime(2024, 1, 2, 3, 4, 5)
        assert (
            substitute_named_with_literals("SELECT :a", {"a": value})
            == "SELECT '2024-01-02 03:04:05'"
        )

    def test_datetime_with_microseconds(self) -> None:
        value = dt.datetime(2024, 1, 2, 3, 4, 5, 678901)
        assert (
            substitute_named_with_literals("SELECT :a", {"a": value})
            == "SELECT '2024-01-02 03:04:05.678901'"
        )

    def test_decimal(self) -> None:
        assert (
            substitute_named_with_literals("SELECT :a", {"a": Decimal("3.14")})
            == "SELECT 3.14"
        )

    def test_bytes(self) -> None:
        assert (
            substitute_named_with_literals("SELECT :a", {"a": b"\xde\xad\xbe\xef"})
            == "SELECT 0xdeadbeef"
        )

    def test_unsupported_type_raises_typeerror(self) -> None:
        with pytest.raises(TypeError, match="Unsupported SQL literal type"):
            substitute_named_with_literals("SELECT :a", {"a": set()})

    def test_placeholder_inside_string_not_substituted(self) -> None:
        assert (
            substitute_named_with_literals("SELECT ':name' AS x", {})
            == "SELECT ':name' AS x"
        )

    def test_placeholder_inside_line_comment_not_substituted(self) -> None:
        sql = "SELECT 1 -- :a\nFROM t"
        assert substitute_named_with_literals(sql, {}) == sql

    def test_placeholder_inside_block_comment_not_substituted(self) -> None:
        sql = "SELECT 1 /* :a */ FROM t"
        assert substitute_named_with_literals(sql, {}) == sql

    def test_repeated_placeholder_substituted_both_times(self) -> None:
        assert (
            substitute_named_with_literals("SELECT :a + :a", {"a": 5}) == "SELECT 5 + 5"
        )

    def test_missing_key_raises_keyerror(self) -> None:
        with pytest.raises(KeyError):
            substitute_named_with_literals("SELECT :a", {})
