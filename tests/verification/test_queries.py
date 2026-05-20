"""Tests for `verify_queries` and `verify_one_query`."""

from __future__ import annotations

from mcp_tools_sql.backends.mssql import MSSQLBackend
from mcp_tools_sql.backends.sqlite import SQLiteBackend
from mcp_tools_sql.config.models import (
    ConnectionConfig,
    QueryConfig,
    QueryParamConfig,
)
from mcp_tools_sql.verification import verify_queries
from mcp_tools_sql.verification.queries import verify_one_query


def test_verify_queries_valid_sqlite(sqlite_backend: SQLiteBackend) -> None:
    """A query with valid SQL + matching params + max_rows_default>0 → all ok=True."""
    queries = {
        "list_customers": QueryConfig(
            sql="SELECT * FROM customers WHERE country = :country",
            params={
                "country": QueryParamConfig(name="country", type="str"),
            },
            max_rows_default=10,
        ),
    }
    result = verify_queries(queries, "sqlite", sqlite_backend)

    assert result["list_customers.sql"]["ok"] is True
    assert result["list_customers.params"]["ok"] is True
    assert result["list_customers.max_rows_default"]["ok"] is True
    assert result["overall_ok"] is True


def test_verify_queries_detects_invalid_sql(sqlite_backend: SQLiteBackend) -> None:
    """Issue test (xii): bad SQL → ``<name>.sql`` row ok=False with sqlite error."""
    queries = {
        "broken": QueryConfig(
            sql="SELECT * FROMX badtable",
            params={},
            max_rows_default=10,
        ),
    }
    result = verify_queries(queries, "sqlite", sqlite_backend)

    assert result["broken.sql"]["ok"] is False
    assert result["broken.sql"]["error"]
    assert result["overall_ok"] is False


def test_verify_queries_detects_param_mismatch(sqlite_backend: SQLiteBackend) -> None:
    """Issue test (xiii): SQL has ``:foo`` but config has ``:bar`` → params ok=False."""
    queries = {
        "mismatch": QueryConfig(
            sql="SELECT * FROM customers WHERE name = :foo",
            params={
                "bar": QueryParamConfig(name="bar", type="str"),
            },
            max_rows_default=10,
        ),
    }
    result = verify_queries(queries, "sqlite", sqlite_backend)

    assert result["mismatch.params"]["ok"] is False
    assert "foo" in result["mismatch.params"]["error"]
    assert "bar" in result["mismatch.params"]["error"]
    assert result["overall_ok"] is False


def test_verify_queries_detects_invalid_param_type(
    sqlite_backend: SQLiteBackend,
) -> None:
    """Param type ``"bool"`` (not in allowed set) → ok=False."""
    queries = {
        "bad_type": QueryConfig(
            sql="SELECT * FROM customers WHERE id = :id",
            params={
                "id": QueryParamConfig(name="id", type="bool"),
            },
            max_rows_default=10,
        ),
    }
    result = verify_queries(queries, "sqlite", sqlite_backend)

    assert result["bad_type.params"]["ok"] is False
    assert "bool" in result["bad_type.params"]["error"]
    assert result["overall_ok"] is False


def test_verify_queries_rejects_filter_and_max_rows_as_non_sql_params(
    sqlite_backend: SQLiteBackend,
) -> None:
    """``filter`` and ``max_rows`` are no longer allow-listed as non-SQL params.

    They are auto-injected by the tool builder, so declaring them in
    ``[queries.<name>.params]`` is now a config error.
    """
    queries = {
        "with_filter": QueryConfig(
            sql="SELECT * FROM customers WHERE country = :country",
            params={
                "country": QueryParamConfig(name="country", type="str"),
                "filter": QueryParamConfig(name="filter", type="str", required=False),
                "max_rows": QueryParamConfig(
                    name="max_rows", type="int", required=False
                ),
            },
            max_rows_default=10,
        ),
    }
    result = verify_queries(queries, "sqlite", sqlite_backend)

    assert result["with_filter.params"]["ok"] is False
    assert "not used in SQL" in result["with_filter.params"]["error"]
    assert result["overall_ok"] is False


def test_verify_queries_detects_missing_max_rows_default(
    sqlite_backend: SQLiteBackend,
) -> None:
    """``QueryConfig(max_rows_default=0)`` → ok=False on ``<name>.max_rows_default`` row."""
    queries = {
        "no_max": QueryConfig(
            sql="SELECT * FROM customers",
            params={},
            max_rows_default=0,
        ),
    }
    result = verify_queries(queries, "sqlite", sqlite_backend)

    assert result["no_max.max_rows_default"]["ok"] is False
    assert "max_rows_default" in result["no_max.max_rows_default"]["error"]
    assert result["overall_ok"] is False


def test_verify_queries_unimplemented_backend_explain_fails_cleanly() -> None:
    """mssql backend's ``explain()`` raises NotImplementedError → ok=False with error."""
    queries = {
        "any": QueryConfig(
            sql="SELECT 1",
            params={},
            max_rows_default=10,
        ),
    }
    conn = ConnectionConfig(backend="mssql", host="localhost", database="db")
    backend = MSSQLBackend(conn)
    result = verify_queries(queries, "mssql", backend)

    assert result["any.sql"]["ok"] is False
    assert result["overall_ok"] is False


def test_verify_one_query_matches_bulk_happy_path(
    sqlite_backend: SQLiteBackend,
) -> None:
    """`verify_one_query` returns identical entries to the bulk function."""
    queries = {
        "list_customers": QueryConfig(
            sql="SELECT * FROM customers WHERE country = :country",
            params={"country": QueryParamConfig(name="country", type="str")},
            max_rows_default=10,
        ),
    }
    bulk = verify_queries(queries, "sqlite", sqlite_backend)
    one = verify_one_query(
        "list_customers", queries["list_customers"], "sqlite", sqlite_backend
    )

    bulk_without_overall = {k: v for k, v in bulk.items() if k != "overall_ok"}
    assert list(one.keys()) == list(bulk_without_overall.keys())
    assert one == bulk_without_overall
