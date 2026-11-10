"""Tests for ``sql_ast.source_queries`` and the opaque ``SourceRef``/``Predicate``.

Owner test: ``parse_source`` turns a user SELECT into an aliased derived-table
reference, and the probe / describe-batch builders render it. Rendered strings
are pinned so the move out of ``summarize/source.py`` stays byte-identical.
"""

from __future__ import annotations

import dataclasses

import pytest

from mcp_tools_sql.sql_ast.placeholders import SqlParseError
from mcp_tools_sql.sql_ast.source_queries import (
    SOURCE_ALIAS,
    build_probe_sql,
    parse_source,
    source_batch_sql,
)
from mcp_tools_sql.sql_ast.summarize_queries import (
    Predicate,
    SourceRef,
    build_table_ref,
    validate_where,
)

# --- parse_source ----------------------------------------------------------


def test_order_by_without_row_limit_is_stripped() -> None:
    """A statement ORDER BY without a row limit is removed from the reference."""
    parsed = parse_source("SELECT a FROM t ORDER BY a", "sqlite")

    assert parsed.ref is not None
    assert parsed.ref.is_query
    assert parsed.order_stripped
    assert not parsed.row_limited
    rendered = parsed.ref.sql(dialect="sqlite")
    assert "ORDER BY" not in rendered
    assert rendered.endswith(f"AS {SOURCE_ALIAS}")
    assert rendered == "(SELECT a FROM t) AS src"


@pytest.mark.parametrize(
    ("sql", "dialect"),
    [
        ("SELECT TOP 5 a FROM t ORDER BY a", "tsql"),
        ("SELECT a FROM t ORDER BY a LIMIT 5", "sqlite"),
    ],
)
def test_row_limited_source_keeps_order_by(sql: str, dialect: str) -> None:
    """With TOP / LIMIT the ORDER BY decides which rows survive, so it is kept."""
    parsed = parse_source(sql, dialect)

    assert parsed.ref is not None
    assert parsed.row_limited
    assert not parsed.order_stripped
    assert "ORDER BY" in parsed.ref.sql(dialect=dialect)


@pytest.mark.parametrize("sql", ["VALUES (1)", "DELETE FROM t"])
def test_non_query_root_has_no_reference(sql: str) -> None:
    """Only ``Select`` / ``Union`` roots produce a reference."""
    parsed = parse_source(sql, "sqlite")

    assert parsed.ref is None
    assert not parsed.row_limited
    assert not parsed.order_stripped


def test_union_root_is_accepted() -> None:
    """A UNION of SELECTs is a query root."""
    parsed = parse_source("SELECT a FROM t UNION SELECT a FROM u", "sqlite")

    assert parsed.ref is not None
    assert parsed.ref.is_query


def test_untokenizable_source_raises_sql_parse_error() -> None:
    """sqlglot errors never escape the boundary untranslated."""
    with pytest.raises(SqlParseError):
        parse_source("SELECT 'x", "sqlite")


# --- build_probe_sql / source_batch_sql ------------------------------------


@pytest.mark.parametrize(
    ("dialect", "expected"),
    [
        ("sqlite", "SELECT * FROM (SELECT a FROM t) AS src LIMIT 5"),
        ("tsql", "SELECT TOP 5 * FROM (SELECT a AS a FROM t) AS src"),
    ],
)
def test_build_probe_sql(dialect: str, expected: str) -> None:
    """The probe is a row-limited ``SELECT *`` over the derived table."""
    parsed = parse_source("SELECT a FROM t", dialect)
    assert parsed.ref is not None

    assert build_probe_sql(parsed.ref, 5, dialect) == expected


def test_build_probe_sql_does_not_mutate_the_reference() -> None:
    """Building the probe leaves the reference's own rendering unchanged."""
    parsed = parse_source("SELECT a FROM t", "sqlite")
    assert parsed.ref is not None
    before = parsed.ref.sql(dialect="sqlite")

    build_probe_sql(parsed.ref, 5, "sqlite")

    assert parsed.ref.sql(dialect="sqlite") == before


def test_source_batch_sql_is_the_inner_select_only() -> None:
    """The describe batch is the re-rendered SELECT, without the alias wrapper."""
    parsed = parse_source("SELECT a FROM t WHERE b = :b ORDER BY a", "tsql")
    assert parsed.ref is not None

    assert source_batch_sql(parsed.ref) == "SELECT a FROM t WHERE b = :b"


# --- SourceRef / Predicate -------------------------------------------------


def test_table_ref_is_not_a_query() -> None:
    """A persisted table reference is not a derived table."""
    assert build_table_ref("dbo", "t", "tsql").is_query is False


def test_source_ref_is_frozen() -> None:
    """``SourceRef`` cannot be re-pointed at another node."""
    ref = build_table_ref("dbo", "t", "sqlite")
    assert isinstance(ref, SourceRef)

    with pytest.raises(dataclasses.FrozenInstanceError):
        ref._node = None  # type: ignore[misc,assignment]


def test_predicate_is_frozen_and_renders() -> None:
    """``validate_where`` returns an opaque, frozen ``Predicate``."""
    ref = build_table_ref("dbo", "t", "sqlite")
    predicate, error = validate_where("a = :v", ref, {"v": 1}, "sqlite")

    assert error is None
    assert isinstance(predicate, Predicate)
    assert predicate.sql(dialect="sqlite") == "a = :v"
    with pytest.raises(dataclasses.FrozenInstanceError):
        predicate._node = None  # type: ignore[misc,assignment]
