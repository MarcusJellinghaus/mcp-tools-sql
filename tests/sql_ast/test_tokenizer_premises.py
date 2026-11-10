"""Premises about sqlglot's tokenizer errors that the read-only gate relies on."""

from __future__ import annotations

import pytest
import sqlglot
from sqlglot.errors import ParseError, SqlglotError, TokenError

from mcp_tools_sql.sql_ast.placeholders import SqlParseError, read_only_violation

_UNTOKENIZABLE = [
    "SELECT 'abc",  # unterminated string literal
    "SELECT 1 /* unterminated",  # unterminated block comment
    "SELECT [abc",  # unterminated bracket
]


@pytest.mark.parametrize("sql", _UNTOKENIZABLE)
@pytest.mark.parametrize("dialect", ["sqlite", "tsql"])
def test_token_error_is_sibling_of_parse_error(sql: str, dialect: str) -> None:
    """sqlglot raises ``TokenError``, a sibling of ``ParseError``, not a subclass."""
    assert issubclass(TokenError, SqlglotError)
    assert not issubclass(TokenError, ParseError)
    with pytest.raises(TokenError):
        sqlglot.parse_one(sql, read=dialect)


@pytest.mark.parametrize("sql", _UNTOKENIZABLE)
@pytest.mark.parametrize("dialect", ["sqlite", "tsql"])
def test_read_only_gate_translates_token_error(sql: str, dialect: str) -> None:
    """The gate surfaces that ``TokenError`` as ``SqlParseError``, class preserved."""
    with pytest.raises(SqlParseError) as excinfo:
        read_only_violation(sql, dialect)
    assert excinfo.value.original_class == "TokenError"
    assert isinstance(excinfo.value.__cause__, TokenError)
