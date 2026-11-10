"""Tests for :class:`SqlParseError` and the :func:`translate_parse_errors` decorator."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
import sqlglot
from sqlglot.errors import ParseError, SqlglotError, TokenError

from mcp_tools_sql.query_helpers import extract_sql_params, read_only_rejection
from mcp_tools_sql.sql_ast.placeholders import (
    SqlParseError,
    build_count_query,
    count_statements,
    extract_param_names,
    first_statement_kind,
    has_leading_cte,
    keyword_absorption_violation,
    passthrough_source_violation,
    read_only_violation,
    single_line,
    substitute_named_with_literals,
    translate_named_to_qmark,
    translate_parse_errors,
)
from mcp_tools_sql.sql_ast.summarize_queries import build_table_ref, validate_where

_UNTERMINATED = "SELECT 'unterminated"


class TestSqlParseError:
    """The exception type itself."""

    def test_str_detail_and_original_class(self) -> None:
        exc = SqlParseError("a\nb", original_class="ParseError")
        assert str(exc) == "a\nb"
        assert exc.detail == "a b"
        assert exc.original_class == "ParseError"

    def test_base_is_plain_exception(self) -> None:
        exc = SqlParseError("x", original_class="ParseError")
        assert isinstance(exc, Exception)
        for base in (RuntimeError, ValueError, KeyError, TypeError):
            assert not isinstance(exc, base)


class TestTranslateParseErrors:
    """The decorator translates sqlglot errors and nothing else."""

    @pytest.mark.parametrize(
        ("raised", "name"),
        [(ParseError("x"), "ParseError"), (TokenError("x"), "TokenError")],
    )
    def test_sqlglot_error_becomes_sql_parse_error(
        self, raised: SqlglotError, name: str
    ) -> None:
        @translate_parse_errors
        def boom() -> None:
            raise raised

        with pytest.raises(SqlParseError) as excinfo:
            boom()
        assert excinfo.value.original_class == name
        assert excinfo.value.__cause__ is raised
        assert str(excinfo.value) == str(raised)

    @pytest.mark.parametrize("raised", [KeyError("k"), ValueError("v")])
    def test_other_exceptions_pass_unchanged(self, raised: Exception) -> None:
        @translate_parse_errors
        def boom() -> None:
            raise raised

        with pytest.raises(type(raised)) as excinfo:
            boom()
        assert excinfo.value is raised

    def test_return_value_passes_through(self) -> None:
        @translate_parse_errors
        def add(a: int, b: int = 0) -> int:
            return a + b

        assert add(1, b=2) == 3


_DECORATED: list[Callable[[str], Any]] = [
    lambda sql: count_statements(sql, "sqlite"),
    lambda sql: extract_param_names(sql, "sqlite"),
    lambda sql: first_statement_kind(sql, "sqlite"),
    lambda sql: translate_named_to_qmark(sql, "sqlite"),
    lambda sql: substitute_named_with_literals(sql, {}, "sqlite"),
    lambda sql: read_only_violation(sql, "sqlite"),
    lambda sql: keyword_absorption_violation(sql, "sqlite"),
    lambda sql: passthrough_source_violation(sql, "sqlite"),
    lambda sql: has_leading_cte(sql, "sqlite"),
    lambda sql: build_count_query(sql, "sqlite"),
]
_DECORATED_IDS = [
    "count_statements",
    "extract_param_names",
    "first_statement_kind",
    "translate_named_to_qmark",
    "substitute_named_with_literals",
    "read_only_violation",
    "keyword_absorption_violation",
    "passthrough_source_violation",
    "has_leading_cte",
    "build_count_query",
]


@pytest.mark.parametrize("call", _DECORATED, ids=_DECORATED_IDS)
def test_decorated_functions_raise_sql_parse_error(call: Callable[[str], Any]) -> None:
    with pytest.raises(SqlParseError) as excinfo:
        call(_UNTERMINATED)
    assert not isinstance(excinfo.value, SqlglotError)
    assert excinfo.value.original_class == "TokenError"


def test_validate_where_returns_verdict_instead_of_raising() -> None:
    predicate, verdict = validate_where(
        "x = 'unterminated", build_table_ref("dbo", "t", "sqlite"), None, "sqlite"
    )
    assert predicate is None
    assert verdict is not None
    assert verdict.startswith("Invalid SQL. TokenError")


def test_extract_sql_params_unparseable_is_empty() -> None:
    assert extract_sql_params("SELECT 'x") == set()


def test_read_only_rejection_message_unchanged() -> None:
    with pytest.raises(TokenError) as excinfo:
        sqlglot.parse_one("SELECT 'x", read="sqlite")
    assert read_only_rejection("SELECT 'x", "sqlite") == (
        "Not read-only. SQL could not be parsed as sqlite: "
        f"{single_line(str(excinfo.value))}"
    )
