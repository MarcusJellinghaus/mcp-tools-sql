"""Tests for the summarize SQL type categoriser."""

from __future__ import annotations

from typing import get_args

import pytest

from mcp_tools_sql.summarize.sql import Category, categorize_type

# (declared_type, dialect, expected_category)
_CASES = [
    # --- SQLite affinities (arbitrary declared-type strings) ---
    ("INTEGER", "sqlite", "numeric"),
    ("INT", "sqlite", "numeric"),
    ("BIGINT", "sqlite", "numeric"),
    ("REAL", "sqlite", "numeric"),
    ("NUMERIC", "sqlite", "numeric"),
    ("NUM", "sqlite", "numeric"),  # bare NUMERIC affinity — must NOT fall to other
    ("DECIMAL(10,2)", "sqlite", "numeric"),
    ("VARCHAR(20)", "sqlite", "string"),
    ("TEXT", "sqlite", "string"),
    ("", "sqlite", "string"),  # empty affinity → string
    ("BLOB", "sqlite", "other"),
    ("BOOLEAN", "sqlite", "boolean"),
    ("DATE", "sqlite", "temporal"),
    ("DATETIME", "sqlite", "temporal"),
    # --- T-SQL DATA_TYPE strings ---
    ("int", "tsql", "numeric"),
    ("bigint", "tsql", "numeric"),
    ("decimal", "tsql", "numeric"),
    ("money", "tsql", "numeric"),
    ("float", "tsql", "numeric"),
    ("bit", "tsql", "boolean"),
    ("nvarchar", "tsql", "string"),
    ("varchar", "tsql", "string"),
    ("nvarchar(max)", "tsql", "string"),  # LOB-ish but still string, NOT other
    ("datetime2", "tsql", "temporal"),
    ("date", "tsql", "temporal"),
    ("varbinary", "tsql", "other"),
    ("uniqueidentifier", "tsql", "other"),
    # LOB trio — cannot appear in GROUP BY / DISTINCT / comparisons
    ("text", "tsql", "other"),
    ("ntext", "tsql", "other"),
    ("image", "tsql", "other"),
    # --- timestamp is dialect-dependent ---
    ("timestamp", "tsql", "other"),  # rowversion = binary(8), NOT date/time
    ("TIMESTAMP", "sqlite", "temporal"),  # genuine date/time affinity
    ("rowversion", "tsql", "other"),
    # --- case-insensitivity ---
    ("Int", "tsql", "numeric"),
    ("VarChar", "sqlite", "string"),
]


@pytest.mark.parametrize(("declared_type", "dialect", "expected"), _CASES)
def test_categorize_type(declared_type: str, dialect: str, expected: str) -> None:
    """categorize_type maps declared types to the expected coarse category."""
    assert categorize_type(declared_type, dialect) == expected


def test_categorize_type_returns_a_category_literal() -> None:
    """Every result is one of the five declared Category literal values."""
    valid = set(get_args(Category))
    for declared_type, dialect, _ in _CASES:
        assert categorize_type(declared_type, dialect) in valid


# --- build_table_ref -------------------------------------------------------


def test_build_table_ref_tsql_includes_schema() -> None:
    """T-SQL table ref bracket-quotes both schema and table."""
    from mcp_tools_sql.summarize.sql import build_table_ref

    ref = build_table_ref("dbo", "t", "tsql")
    assert ref.sql(dialect="tsql") == "[dbo].[t]"


def test_build_table_ref_tsql_quotes_names_with_spaces() -> None:
    """T-SQL table ref survives spaces/reserved words via quoting."""
    from mcp_tools_sql.summarize.sql import build_table_ref

    ref = build_table_ref("Sales", "Order Details", "tsql")
    assert ref.sql(dialect="tsql") == "[Sales].[Order Details]"


def test_build_table_ref_sqlite_omits_schema() -> None:
    """SQLite has no schema namespace, so only the table renders."""
    from mcp_tools_sql.summarize.sql import build_table_ref

    ref = build_table_ref("ignored", "t", "sqlite")
    assert ref.sql(dialect="sqlite") == '"t"'


# --- metadata_sql ----------------------------------------------------------


def test_metadata_sql_tsql_uses_information_schema() -> None:
    """T-SQL metadata query reads INFORMATION_SCHEMA.COLUMNS with bound params."""
    from mcp_tools_sql.summarize.sql import metadata_sql

    sql = metadata_sql("tsql")
    assert "INFORMATION_SCHEMA.COLUMNS" in sql
    assert ":schema" in sql
    assert ":table" in sql


def test_metadata_sql_sqlite_uses_pragma_table_info() -> None:
    """SQLite metadata query reads pragma_table_info with a bound table."""
    from mcp_tools_sql.summarize.sql import metadata_sql

    sql = metadata_sql("sqlite")
    assert "pragma_table_info(:table)" in sql


# --- build_count_sql -------------------------------------------------------


def test_build_count_sql_tsql_no_predicate() -> None:
    """Unfiltered T-SQL count aliases row_count over the bracketed table."""
    from mcp_tools_sql.summarize.sql import build_count_sql, build_table_ref

    ref = build_table_ref("dbo", "t", "tsql")
    sql = build_count_sql(ref, None, "tsql")
    assert sql == "SELECT COUNT(*) AS row_count FROM [dbo].[t]"


def test_build_count_sql_sqlite_no_predicate() -> None:
    """Unfiltered SQLite count omits schema and double-quotes the table."""
    from mcp_tools_sql.summarize.sql import build_count_sql, build_table_ref

    ref = build_table_ref("ignored", "t", "sqlite")
    sql = build_count_sql(ref, None, "sqlite")
    assert sql == 'SELECT COUNT(*) AS row_count FROM "t"'


def test_build_count_sql_includes_predicate() -> None:
    """A validated predicate renders into the count query's WHERE clause."""
    from mcp_tools_sql.summarize.sql import (
        build_count_sql,
        build_table_ref,
        validate_where,
    )

    predicate, error = validate_where("status = :s", "dbo", "t", {"s": "x"}, "sqlite")
    assert error is None
    ref = build_table_ref("dbo", "t", "sqlite")
    sql = build_count_sql(ref, predicate, "sqlite")
    assert sql == 'SELECT COUNT(*) AS row_count FROM "t" WHERE status = :s'


# --- validate_where --------------------------------------------------------


@pytest.mark.parametrize("where", [None, "", "   "])
def test_validate_where_blank_returns_no_predicate(where: str | None) -> None:
    """None/blank where yields (None, None) -- no filter, no error."""
    from mcp_tools_sql.summarize.sql import validate_where

    assert validate_where(where, "dbo", "t", None, "sqlite") == (None, None)


def test_validate_where_valid_predicate_returns_ast() -> None:
    """A bound predicate returns a re-rendered AST, never the raw text."""
    from mcp_tools_sql.summarize.sql import validate_where

    predicate, error = validate_where(
        "status = :s", "dbo", "t", {"s": "open"}, "sqlite"
    )
    assert error is None
    assert predicate is not None
    assert predicate.sql(dialect="sqlite") == "status = :s"


def test_validate_where_rejects_write_smuggling() -> None:
    """A predicate smuggling a write is rejected fail-closed.

    A ``DELETE`` buried in a subquery never parses as a read-only predicate:
    SQLite's parser rejects it, so ``basic_preflight``'s parse check fires (the
    ``read_only_violation`` AST gate is the defence-in-depth backstop). Either
    way the predicate is refused and no data query is built.
    """
    from mcp_tools_sql.summarize.sql import validate_where

    predicate, error = validate_where(
        "id IN (DELETE FROM t)", "dbo", "t", None, "sqlite"
    )
    assert predicate is None
    assert error is not None


def test_validate_where_rejects_statement_terminator() -> None:
    """A stacked statement is rejected before any query runs."""
    from mcp_tools_sql.summarize.sql import validate_where

    predicate, error = validate_where(
        "1=1); DROP TABLE t --", "dbo", "t", None, "sqlite"
    )
    assert predicate is None
    assert error is not None


def test_validate_where_missing_param_verdict() -> None:
    """An unbound :name without params fails via basic_preflight."""
    from mcp_tools_sql.summarize.sql import validate_where

    predicate, error = validate_where("x = :missing", "dbo", "t", None, "sqlite")
    assert predicate is None
    assert error is not None
    assert "missing parameter" in error.lower()
