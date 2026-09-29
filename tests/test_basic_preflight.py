"""Direct unit tests for the shared ``basic_preflight`` helper.

``basic_preflight`` is the pre-flight every SQL-consuming tool runs before its
own gates, so it is tested here on its own rather than only through one tool.
The tool-level tests in ``test_validation_tools.py``, ``test_count_tools.py``
and ``tests/summarize/`` assert that each call site surfaces these verdicts;
this module asserts the verdicts themselves.
"""

from __future__ import annotations

import pytest
import sqlglot
from sqlglot.errors import TokenError

from mcp_tools_sql.utils.sql_placeholders import (
    ParseError,
    basic_preflight,
    count_statements,
    single_line,
)

UNTOKENIZABLE = [
    "SELECT 'abc",  # unterminated string literal
    "SELECT 1 /* unterminated",  # unterminated block comment
    "SELECT [abc",  # unterminated bracket
]

ZERO_STATEMENT = [
    "-- hi",  # line comment only
    "/* hi */",  # block comment only
    ";",  # separator only
]

NO_STATEMENT_VERDICT = (
    "Invalid SQL. ValidationError: no statement found — "
    "the SQL contains only comments or separators"
)


class TestBasicPreflight:
    """Direct unit tests for the shared :func:`basic_preflight` helper."""

    def test_empty_sql(self) -> None:
        assert (
            basic_preflight("", None, "sqlite")
            == "Invalid SQL. ValidationError: empty SQL"
        )

    def test_whitespace_only_sql(self) -> None:
        assert (
            basic_preflight("  \n\t ", None, "sqlite")
            == "Invalid SQL. ValidationError: empty SQL"
        )

    def test_multiple_statements(self) -> None:
        assert (
            basic_preflight("SELECT 1; SELECT 2", None, "sqlite")
            == "Invalid SQL. ValidationError: multiple statements not supported"
        )

    @pytest.mark.parametrize("sql", ZERO_STATEMENT)
    @pytest.mark.parametrize("dialect", ["sqlite", "tsql"])
    def test_zero_statements(self, sql: str, dialect: str) -> None:
        """Non-empty SQL that parses to no statement gets its own verdict.

        ``sqlglot.parse`` returns ``[None]`` for these, so the count is 0 --
        neither the empty check nor the ``> 1`` check fires, and the parse
        succeeds. Only an explicit zero check keeps the downstream
        ``parse_one`` from raising out of the tool.
        """
        assert count_statements(sql, dialect) == 0
        assert basic_preflight(sql, None, dialect) == NO_STATEMENT_VERDICT

    def test_missing_param(self) -> None:
        assert (
            basic_preflight("SELECT :x", None, "sqlite")
            == "Invalid parameters. ValidationError: missing parameter: x"
        )

    def test_unparseable_returns_parse_error(self) -> None:
        verdict = basic_preflight("SELECT FROM WHERE", None, "sqlite")
        assert verdict is not None
        assert verdict.startswith("Invalid SQL. ParseError (SQL parsed as ")

    def test_verdict_is_one_line_without_escapes(self) -> None:
        """sqlglot's multi-line, ANSI-underlined error text is flattened.

        A verdict is returned as one tool result line, so neither the newline
        nor the terminal control codes sqlglot emits may survive.
        """
        with pytest.raises(ParseError) as excinfo:
            sqlglot.parse("SELECT FROM WHERE", read="sqlite")
        raw = str(excinfo.value)
        assert "\n" in raw
        assert "\x1b" in raw

        verdict = basic_preflight("SELECT FROM WHERE", None, "sqlite")
        assert verdict is not None
        assert "\n" not in verdict
        assert "\x1b" not in verdict
        assert single_line(raw) in verdict

    @pytest.mark.parametrize("sql", UNTOKENIZABLE)
    @pytest.mark.parametrize("dialect", ["sqlite", "tsql"])
    def test_untokenizable_returns_token_error(self, sql: str, dialect: str) -> None:
        """``TokenError`` is caught too, and names itself in the verdict.

        ``TokenError`` is a sibling of ``ParseError``, not a subclass, so the
        narrower catch let it escape. The class name is read off the raised
        exception, which is why the verdict says ``TokenError`` here and
        ``ParseError`` above.
        """
        with pytest.raises(TokenError) as excinfo:
            sqlglot.parse(sql, read=dialect)
        verdict = basic_preflight(sql, None, dialect)
        assert verdict == (
            f"Invalid SQL. TokenError (SQL parsed as {dialect}): "
            f"{single_line(str(excinfo.value))}"
        )

    def test_valid_sql_passes(self) -> None:
        assert basic_preflight("SELECT 1", None, "sqlite") is None

    def test_does_not_reject_session_keywords(self) -> None:
        # USE/SET/DECLARE are NOT rejected here: the session-keyword check
        # lives only in validate_sql's _preflight, layered on top.
        assert basic_preflight("USE other_db", None, "tsql") is None
        assert basic_preflight("SET QUOTED_IDENTIFIER ON", None, "tsql") is None
        assert basic_preflight("DECLARE @x INT", None, "tsql") is None
