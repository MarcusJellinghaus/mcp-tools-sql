"""Tests for the summarize source resolver (``summarize/source.py``).

Three concerns, all exercised without a real database: ``validate_source`` turns
a user SELECT into a validated, aliased derived-table reference (reusing the
shared preflight / read-only / leading-CTE gates), ``probe_columns`` resolves
that reference's output columns from a few-row value probe against a
``MagicMock`` backend returning canned ``(names, rows)``, and
``build_table_source`` resolves the persisted-table path from canned catalog
rows.

The probe's Python-value -> declared-type mapping is dialect-dependent on
purpose; the T-SQL string row (``nvarchar``, never ``TEXT``) and the SQLite
temporal/boolean divergence are each pinned by their own regression test.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlglot import exp

from mcp_tools_sql.summarize.source import (
    ORDER_BY_STRIPPED_NOTE,
    PROBE_ROWS,
    ROW_LIMITED_NOTE,
    SQLITE_PROBE_TYPE_LIMITS_NOTE,
    TYPES_PROBED_NOTE,
    UNKNOWN_TYPE,
    UNKNOWN_TYPE_NOTE,
    Source,
    build_table_source,
    probe_columns,
    validate_source,
)
from mcp_tools_sql.utils.sql_placeholders import LEADING_CTE_REJECTION


def _ref(sql: str, dialect: str, params: dict[str, Any] | None = None) -> exp.Subquery:
    """Validate ``sql`` and return its reference, asserting it was accepted.

    Returns:
        The aliased derived-table reference for ``sql``.
    """
    ref, _notes, error = validate_source(sql, params, dialect)
    assert error is None
    assert ref is not None
    return ref


def _backend(columns: list[str], rows: list[tuple[Any, ...]]) -> MagicMock:
    """Build a backend double whose probe returns ``(columns, rows)``.

    Returns:
        The configured :class:`MagicMock` backend.
    """
    backend = MagicMock()
    backend.execute_readonly_query_with_columns.return_value = (columns, rows)
    return backend


# --- validate_source -------------------------------------------------------


@pytest.mark.parametrize(
    ("dialect", "rendered"),
    [
        ("sqlite", "(SELECT a FROM t) AS src"),
        # The T-SQL generator makes the implicit projection alias explicit.
        ("tsql", "(SELECT a AS a FROM t) AS src"),
    ],
)
def test_plain_select_becomes_aliased_subquery(dialect: str, rendered: str) -> None:
    """A plain SELECT renders as a derived table aliased ``AS src``."""
    ref, notes, error = validate_source("SELECT a FROM t", None, dialect)

    assert error is None
    assert notes == []
    assert isinstance(ref, exp.Subquery)
    assert ref.sql(dialect=dialect) == rendered


@pytest.mark.parametrize(
    ("sql", "dialect", "fragment"),
    [
        ("INSERT INTO t VALUES (1)", "sqlite", "INSERT"),
        ("DROP TABLE t", "sqlite", "DROP"),
        ("SELECT a INTO t2 FROM t", "tsql", "SELECT ... INTO"),
    ],
)
def test_write_statements_rejected(sql: str, dialect: str, fragment: str) -> None:
    """The shared read-only gate rejects writes before any reference is built."""
    ref, notes, error = validate_source(sql, None, dialect)

    assert ref is None
    assert notes == []
    assert error is not None
    assert error.startswith("Not read-only.")
    assert fragment in error


@pytest.mark.parametrize("dialect", ["sqlite", "tsql"])
def test_values_root_rejected_by_allow_list(dialect: str) -> None:
    """``VALUES`` passes ``read_only_violation`` but fails the root allow-list.

    ``read_only_violation`` accepts ``exp.Values`` as a countable root; a
    profiling *source* must be a query, so the narrower allow-list here
    (``Select`` / ``Union`` only) rejects it with its own message.
    """
    ref, _notes, error = validate_source("VALUES (1), (2)", None, dialect)

    assert ref is None
    assert error is not None
    assert not error.startswith("Not read-only.")
    assert "SELECT" in error


@pytest.mark.parametrize(
    ("sql", "params", "fragment"),
    [
        ("SELECT 1; SELECT 2", None, "multiple statements"),
        ("", None, "empty SQL"),
        ("   ", None, "empty SQL"),
        ("SELECT FROM WHERE", None, "ParseError"),
        ("SELECT a FROM t WHERE b = :missing", None, "missing parameter"),
    ],
)
def test_preflight_verdicts_pass_through(
    sql: str, params: dict[str, Any] | None, fragment: str
) -> None:
    """Multi-statement / empty / unparseable / unbound ``:name`` verdicts."""
    ref, notes, error = validate_source(sql, params, "sqlite")

    assert ref is None
    assert notes == []
    assert error is not None
    assert fragment in error


def test_leading_cte_rejected_on_tsql() -> None:
    """A leading ``WITH`` cannot be wrapped in a T-SQL derived table."""
    sql = "WITH c AS (SELECT a FROM t) SELECT a FROM c"

    ref, _notes, error = validate_source(sql, None, "tsql")

    assert ref is None
    assert error == LEADING_CTE_REJECTION


def test_leading_cte_accepted_on_sqlite() -> None:
    """SQLite allows a CTE inside a derived table, so it is not rejected."""
    sql = "WITH c AS (SELECT a FROM t) SELECT a FROM c"

    ref, notes, error = validate_source(sql, None, "sqlite")

    assert error is None
    assert notes == []
    assert ref is not None
    assert "WITH c AS" in ref.sql(dialect="sqlite")


def test_order_by_without_limit_is_stripped() -> None:
    """Without a row limit ``ORDER BY`` is meaningless: strip it and say so."""
    ref, notes, error = validate_source(
        "SELECT a FROM t ORDER BY a DESC", None, "sqlite"
    )

    assert error is None
    assert ref is not None
    assert "ORDER BY" not in ref.sql(dialect="sqlite").upper()
    assert notes == [ORDER_BY_STRIPPED_NOTE]


@pytest.mark.parametrize(
    ("sql", "dialect"),
    [
        ("SELECT TOP 10 a FROM t ORDER BY a DESC", "tsql"),
        ("SELECT a FROM t ORDER BY a DESC LIMIT 10", "sqlite"),
        ("SELECT a FROM t ORDER BY a OFFSET 5 ROWS FETCH NEXT 10 ROWS ONLY", "tsql"),
    ],
)
def test_row_limited_source_keeps_order_by(sql: str, dialect: str) -> None:
    """With a row limit the ``ORDER BY`` decides *which* rows are profiled."""
    ref, notes, error = validate_source(sql, None, dialect)

    assert error is None
    assert ref is not None
    assert "ORDER BY" in ref.sql(dialect=dialect).upper()
    assert notes == [ROW_LIMITED_NOTE]
    assert ORDER_BY_STRIPPED_NOTE not in notes


def test_placeholders_survive_into_the_reference() -> None:
    """``:name`` placeholders inside the source are preserved for binding."""
    ref, _notes, error = validate_source(
        "SELECT a FROM t WHERE b = :b", {"b": 1}, "sqlite"
    )

    assert error is None
    assert ref is not None
    assert ":b" in ref.sql(dialect="sqlite")


# --- probe_columns ---------------------------------------------------------


@pytest.mark.parametrize(
    ("dialect", "string_type"),
    [("sqlite", "TEXT"), ("tsql", "nvarchar")],
)
def test_probe_maps_common_python_types(dialect: str, string_type: str) -> None:
    """int / float / bytes / str -- the four types SQLite can ever yield."""
    backend = _backend(
        ["n", "f", "b", "s"],
        [(1, 1.5, b"\x00", "hello")],
    )

    metas, error = probe_columns(
        backend, _ref("SELECT * FROM t", dialect), None, dialect
    )

    assert error is None
    assert metas is not None
    assert [m.name for m in metas] == ["n", "f", "b", "s"]
    assert [m.ordinal for m in metas] == [0, 1, 2, 3]
    assert [m.declared_type for m in metas] == ["INTEGER", "REAL", "BLOB", string_type]
    assert [m.category for m in metas] == ["numeric", "numeric", "other", "string"]
    assert all(m.note == "" for m in metas)


def test_probe_maps_tsql_only_python_types() -> None:
    """bool / Decimal / datetime / date reach the probe only through pyodbc."""
    backend = _backend(
        ["flag", "amount", "at", "day"],
        [(True, Decimal("1.50"), datetime(2020, 1, 1, 12, 0), date(2020, 1, 1))],
    )

    metas, error = probe_columns(backend, _ref("SELECT * FROM t", "tsql"), None, "tsql")

    assert error is None
    assert metas is not None
    assert [m.declared_type for m in metas] == ["bit", "decimal", "datetime", "date"]
    assert [m.category for m in metas] == [
        "boolean",
        "numeric",
        "temporal",
        "temporal",
    ]


def test_probed_string_is_nvarchar_on_tsql_not_lob() -> None:
    """A probed ``str`` must categorise ``string`` on T-SQL, never ``other``.

    ``categorize_type`` sweeps the T-SQL LOB trio (``text`` / ``ntext`` /
    ``image``) into ``other``, so typing a probed string as ``TEXT`` would strip
    every string column of its distinct count, length stats, and value list on
    exactly the path where the probe is the only type resolver.
    """
    from mcp_tools_sql.summarize.sql import build_scalar_sql, build_value_list_sql

    ref = _ref("SELECT * FROM t", "tsql")
    metas, error = probe_columns(_backend(["s"], [("hello",)]), ref, None, "tsql")

    assert error is None
    assert metas is not None
    assert metas[0].declared_type == "nvarchar"
    assert metas[0].category == "string"

    scalar = build_scalar_sql(metas, ref, None, "tsql", include_distinct=True)
    assert "COUNT(DISTINCT" in scalar
    assert "LEN(" in scalar
    assert "c0__min" in scalar
    assert "DATALENGTH" not in scalar

    values = build_value_list_sql(metas[0], ref, None, 5, "tsql", kind="top")
    assert "GROUP BY" in values


def test_probed_string_stays_text_on_sqlite() -> None:
    """SQLite keeps ``TEXT`` so the rendered type matches the table path."""
    ref = _ref("SELECT * FROM t", "sqlite")
    metas, error = probe_columns(_backend(["s"], [("hello",)]), ref, None, "sqlite")

    assert error is None
    assert metas is not None
    assert metas[0].declared_type == "TEXT"
    assert metas[0].category == "string"


def test_sqlite_probe_cannot_see_declared_types() -> None:
    """Pin the documented SQLite divergence: dates are strings, bools ints.

    ``backends/sqlite.py`` connects without ``detect_types``, so a DATE column
    arrives as ``str`` and a BOOLEAN column as ``int``. The gap is surfaced to
    the caller via :data:`SQLITE_PROBE_TYPE_LIMITS_NOTE`, not worked around.
    """
    ref = _ref("SELECT * FROM t", "sqlite")
    metas, error = probe_columns(
        _backend(["created", "is_active"], [("2020-01-01", 1)]), ref, None, "sqlite"
    )

    assert error is None
    assert metas is not None
    assert (metas[0].declared_type, metas[0].category) == ("TEXT", "string")
    assert (metas[1].declared_type, metas[1].category) == ("INTEGER", "numeric")

    assert "DATE/DATETIME" in SQLITE_PROBE_TYPE_LIMITS_NOTE
    assert "BOOLEAN" in SQLITE_PROBE_TYPE_LIMITS_NOTE
    assert "schema=" in SQLITE_PROBE_TYPE_LIMITS_NOTE
    assert "table=" in SQLITE_PROBE_TYPE_LIMITS_NOTE
    assert TYPES_PROBED_NOTE.strip() != ""


def test_tsql_probe_sees_real_temporal_and_boolean_values() -> None:
    """The same two columns keep their catalog-like types through pyodbc."""
    ref = _ref("SELECT * FROM t", "tsql")
    metas, error = probe_columns(
        _backend(["created", "is_active"], [(date(2020, 1, 1), True)]),
        ref,
        None,
        "tsql",
    )

    assert error is None
    assert metas is not None
    assert (metas[0].declared_type, metas[0].category) == ("date", "temporal")
    assert (metas[1].declared_type, metas[1].category) == ("bit", "boolean")


def test_all_null_column_resolves_unknown_with_note() -> None:
    """No sampled value can decide a type: say so inline, profile as string."""
    ref = _ref("SELECT * FROM t", "sqlite")
    metas, error = probe_columns(
        _backend(["note"], [(None,), (None,)]), ref, None, "sqlite"
    )

    assert error is None
    assert metas is not None
    assert metas[0].declared_type == UNKNOWN_TYPE
    assert metas[0].category == "string"
    assert metas[0].note == UNKNOWN_TYPE_NOTE
    assert metas[0].note != ""


def test_zero_rows_resolves_every_column_unknown() -> None:
    """An empty probe result resolves without raising."""
    ref = _ref("SELECT * FROM t", "sqlite")
    metas, error = probe_columns(_backend(["a", "b"], []), ref, None, "sqlite")

    assert error is None
    assert metas is not None
    assert [m.declared_type for m in metas] == [UNKNOWN_TYPE, UNKNOWN_TYPE]
    assert [m.category for m in metas] == ["string", "string"]


def test_first_non_null_value_decides_the_type() -> None:
    """A leading NULL does not make the column unknown."""
    ref = _ref("SELECT * FROM t", "sqlite")
    metas, error = probe_columns(
        _backend(["a"], [(None,), (7,), ("x",)]), ref, None, "sqlite"
    )

    assert error is None
    assert metas is not None
    assert metas[0].declared_type == "INTEGER"
    assert metas[0].note == ""


@pytest.mark.parametrize(
    "names",
    [
        ["id", "name", "id", "country"],  # duplicate, as SQLite really returns it
        ["id", "ID"],  # duplicate only case-insensitively
        ["id", ""],  # unnamed expression column
        ["id", "id:1"],  # a disambiguating suffix, wherever it appears
    ],
)
def test_ambiguous_output_names_are_rejected(names: list[str]) -> None:
    """Duplicate / unnamed / suffixed names fail the call, naming the recovery."""
    ref = _ref("SELECT * FROM t", "sqlite")
    rows = [tuple(range(len(names)))]

    metas, error = probe_columns(_backend(names, rows), ref, None, "sqlite")

    assert metas is None
    assert error is not None
    assert "duplicate or unnamed output columns" in error
    assert "AS" in error  # names the aliasing recovery


@pytest.mark.parametrize(
    ("dialect", "fragment"),
    [("sqlite", f"LIMIT {PROBE_ROWS}"), ("tsql", f"TOP {PROBE_ROWS}")],
)
def test_probe_sql_is_row_limited_and_forwards_params(
    dialect: str, fragment: str
) -> None:
    """The probe samples a few rows and binds the source's own placeholders."""
    backend = _backend(["a"], [(1,)])
    params = {"b": 1}
    ref = _ref("SELECT a FROM t WHERE b = :b", dialect, params)

    metas, error = probe_columns(backend, ref, params, dialect)

    assert error is None
    assert metas is not None
    probe_sql, passed_params = backend.execute_readonly_query_with_columns.call_args[0]
    assert fragment in probe_sql
    assert ":b" in probe_sql
    assert passed_params is params


def test_probe_sql_is_built_from_the_parsed_source() -> None:
    """The probe re-renders the parsed source; raw user text is never echoed."""
    backend = _backend(["a"], [(1,)])
    ref = _ref("select    a\n  from   t", "sqlite")

    probe_columns(backend, ref, None, "sqlite")

    probe_sql = backend.execute_readonly_query_with_columns.call_args[0][0]
    assert probe_sql == f"SELECT * FROM (SELECT a FROM t) AS src LIMIT {PROBE_ROWS}"


# --- build_table_source ----------------------------------------------------


def _catalog_backend(rows: list[dict[str, Any]]) -> MagicMock:
    """Build a backend double whose metadata query returns ``rows``.

    Returns:
        The configured :class:`MagicMock` backend.
    """
    backend = MagicMock()
    backend.execute_readonly_query.return_value = rows
    return backend


@pytest.mark.parametrize(
    ("dialect", "schema", "label", "string_type"),
    [
        ("tsql", "dbo", "dbo.orders", "nvarchar"),
        ("sqlite", "main", "main.orders", "TEXT"),
    ],
)
def test_build_table_source_from_catalog_rows(
    dialect: str, schema: str, label: str, string_type: str
) -> None:
    """The catalog rows become the metas; the label is ``schema.table`` on both.

    ``label`` is a *message* descriptor, not a SQL reference: the status
    messages print the schema on SQLite too, so it never drops the schema the
    way ``build_table_ref`` does.
    """
    backend = _catalog_backend(
        [
            {"name": "id", "type": "INTEGER", "ordinal": 0},
            {"name": "Note", "type": string_type, "ordinal": 1},
        ]
    )

    built = build_table_source(backend, schema, "orders", dialect)

    assert isinstance(built, Source)
    assert built.label == label
    assert [m.name for m in built.metas] == ["id", "Note"]  # declared casing kept
    assert [m.declared_type for m in built.metas] == ["INTEGER", string_type]
    assert [m.category for m in built.metas] == ["numeric", "string"]
    assert [m.ordinal for m in built.metas] == [0, 1]
    assert built.notes == []
    assert built.types_probed is False
    assert isinstance(built.ref, exp.Table)

    meta_sql, meta_params = backend.execute_readonly_query.call_args[0]
    assert meta_params == {"schema": schema, "table": "orders"}
    assert "orders" not in meta_sql  # bound, never concatenated


def test_build_table_source_empty_metadata_returns_not_found() -> None:
    """No metadata rows is the not-found message, not an empty profile."""
    built = build_table_source(_catalog_backend([]), "dbo", "orders", "tsql")

    assert built == (
        "Table dbo.orders not found (no such table or no columns). "
        "Check the schema and table name."
    )
