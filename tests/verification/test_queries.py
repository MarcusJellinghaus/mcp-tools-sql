"""Tests for `verify_queries` and `verify_one_query`."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from mcp_tools_sql.backends.mssql import MSSQLBackend
from mcp_tools_sql.backends.registry import BackendRegistry
from mcp_tools_sql.backends.sqlite import SQLiteBackend
from mcp_tools_sql.config.models import (
    BackendQueryConfig,
    ConnectionConfig,
    QueryConfig,
    QueryParamConfig,
    ResolvedTarget,
    ResolvedTargets,
)
from mcp_tools_sql.verification import verify_queries
from mcp_tools_sql.verification.queries import verify_one_query

from .conftest import StubRegistry, all_reachable_map, make_targets


def test_verify_queries_valid_sqlite(
    sqlite_targets: ResolvedTargets,
    sqlite_registry: BackendRegistry,
    all_reachable: dict[tuple[str, str], bool],
) -> None:
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
    result = verify_queries(queries, sqlite_targets, sqlite_registry, all_reachable)

    assert result["list_customers.sql"]["ok"] is True
    assert result["list_customers.params"]["ok"] is True
    assert result["list_customers.max_rows_default"]["ok"] is True
    assert result["overall_ok"] is True


def test_verify_queries_detects_invalid_sql(
    sqlite_targets: ResolvedTargets,
    sqlite_registry: BackendRegistry,
    all_reachable: dict[tuple[str, str], bool],
) -> None:
    """Issue test (xii): bad SQL → ``<name>.sql`` row ok=False with sqlite error.

    The SQL is read-only and parseable, so it reaches EXPLAIN; only the table
    is missing. A statement the gate rejects never gets EXPLAINed at all --
    see :func:`test_sql_row_skipped_when_query_is_not_read_only`.
    """
    queries = {
        "broken": QueryConfig(
            sql="SELECT * FROM badtable",
            params={},
            max_rows_default=10,
        ),
    }
    result = verify_queries(queries, sqlite_targets, sqlite_registry, all_reachable)

    assert result["broken.sql"]["ok"] is False
    assert result["broken.sql"]["error"]
    assert result["overall_ok"] is False


def test_verify_queries_detects_param_mismatch(
    sqlite_targets: ResolvedTargets,
    sqlite_registry: BackendRegistry,
    all_reachable: dict[tuple[str, str], bool],
) -> None:
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
    result = verify_queries(queries, sqlite_targets, sqlite_registry, all_reachable)

    assert result["mismatch.params"]["ok"] is False
    assert "foo" in result["mismatch.params"]["error"]
    assert "bar" in result["mismatch.params"]["error"]
    assert result["overall_ok"] is False


def test_verify_queries_detects_invalid_param_type(
    sqlite_targets: ResolvedTargets,
    sqlite_registry: BackendRegistry,
    all_reachable: dict[tuple[str, str], bool],
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
    result = verify_queries(queries, sqlite_targets, sqlite_registry, all_reachable)

    assert result["bad_type.params"]["ok"] is False
    assert "bool" in result["bad_type.params"]["error"]
    assert result["overall_ok"] is False


def test_verify_queries_rejects_filter_and_max_rows_as_non_sql_params(
    sqlite_targets: ResolvedTargets,
    sqlite_registry: BackendRegistry,
    all_reachable: dict[tuple[str, str], bool],
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
    result = verify_queries(queries, sqlite_targets, sqlite_registry, all_reachable)

    assert result["with_filter.params"]["ok"] is False
    assert "not used in SQL" in result["with_filter.params"]["error"]
    assert result["overall_ok"] is False


def test_verify_queries_detects_missing_max_rows_default(
    sqlite_targets: ResolvedTargets,
    sqlite_registry: BackendRegistry,
    all_reachable: dict[tuple[str, str], bool],
) -> None:
    """``QueryConfig(max_rows_default=0)`` → ok=False on ``<name>.max_rows_default`` row."""
    queries = {
        "no_max": QueryConfig(
            sql="SELECT * FROM customers",
            params={},
            max_rows_default=0,
        ),
    }
    result = verify_queries(queries, sqlite_targets, sqlite_registry, all_reachable)

    assert result["no_max.max_rows_default"]["ok"] is False
    assert "max_rows_default" in result["no_max.max_rows_default"]["error"]
    assert result["overall_ok"] is False


def test_verify_queries_detects_non_positive_max_rows_hard(
    sqlite_targets: ResolvedTargets,
    sqlite_registry: BackendRegistry,
    all_reachable: dict[tuple[str, str], bool],
) -> None:
    """``max_rows_hard=0`` → ok=False on the ``<name>.max_rows_hard`` row."""
    queries = {
        "no_hard": QueryConfig(
            sql="SELECT * FROM customers",
            params={},
            max_rows_default=10,
            max_rows_hard=0,
        ),
        "healthy": QueryConfig(
            sql="SELECT * FROM customers",
            params={},
            max_rows_default=10,
            max_rows_hard=50,
        ),
    }
    result = verify_queries(queries, sqlite_targets, sqlite_registry, all_reachable)

    assert result["no_hard.max_rows_hard"]["ok"] is False
    assert "max_rows_hard" in result["no_hard.max_rows_hard"]["error"]
    assert result["healthy.max_rows_hard"]["ok"] is True
    assert result["overall_ok"] is False


def test_verify_queries_unresolvable_pin_emits_all_four_rows(
    sqlite_targets: ResolvedTargets,
    sqlite_registry: BackendRegistry,
    all_reachable: dict[tuple[str, str], bool],
) -> None:
    """An unresolvable pin still emits the full four-row contract, all failing."""
    queries = {
        "bad_pin": QueryConfig(
            sql="SELECT * FROM customers",
            params={},
            max_rows_default=10,
            max_rows_hard=50,
            connection="nope",
        ),
    }
    result = verify_queries(queries, sqlite_targets, sqlite_registry, all_reachable)

    for suffix in ("sql", "params", "max_rows_default", "max_rows_hard"):
        assert result[f"bad_pin.{suffix}"]["ok"] is False
        assert "nope" in result[f"bad_pin.{suffix}"]["error"]
    assert result["bad_pin.max_rows_hard"]["value"] == "(skipped)"
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
    targets = make_targets(backend_name="mssql", config=conn)
    registry = StubRegistry(backend)
    result = verify_queries(queries, targets, registry, all_reachable_map(targets))

    assert result["any.sql"]["ok"] is False
    assert result["overall_ok"] is False


def test_verify_one_query_matches_bulk_happy_path(
    sqlite_targets: ResolvedTargets,
    sqlite_registry: BackendRegistry,
    all_reachable: dict[tuple[str, str], bool],
) -> None:
    """`verify_one_query` returns identical entries to the bulk function."""
    queries = {
        "list_customers": QueryConfig(
            sql="SELECT * FROM customers WHERE country = :country",
            params={"country": QueryParamConfig(name="country", type="str")},
            max_rows_default=10,
        ),
    }
    bulk = verify_queries(queries, sqlite_targets, sqlite_registry, all_reachable)
    one = verify_one_query(
        "list_customers",
        queries["list_customers"],
        sqlite_targets,
        sqlite_registry,
        all_reachable,
    )

    bulk_without_overall = {k: v for k, v in bulk.items() if k != "overall_ok"}
    assert list(one.keys()) == list(bulk_without_overall.keys())
    assert one == bulk_without_overall


# ---------------------------------------------------------------------------
# Per-target EXPLAIN / skip (step 15)
# ---------------------------------------------------------------------------


def test_verify_queries_skips_query_pinned_to_unreachable_connection(
    sqlite_backend: SQLiteBackend,
) -> None:
    """A query pinned to a down connection is skipped, naming that connection.

    A reachable query in the same run still gets a real EXPLAIN verdict — the
    skip must not blank the whole M2 section.
    """
    prod = ResolvedTarget(
        connection="prod",
        database="main",
        config=ConnectionConfig(backend="sqlite", path=":memory:"),
        backend_name="sqlite",
        is_default=False,
    )
    default = ResolvedTarget(
        connection="default",
        database="main",
        config=ConnectionConfig(backend="sqlite", path=":memory:"),
        backend_name="sqlite",
        is_default=True,
    )
    targets = ResolvedTargets(
        targets=[default, prod],
        default=default,
        file_default_connection="default",
    )
    registry = StubRegistry(sqlite_backend)
    reachable = {
        ("default", "main"): True,
        ("prod", "main"): False,
    }

    queries = {
        "reachable_one": QueryConfig(
            sql="SELECT * FROM customers WHERE country = :country",
            params={"country": QueryParamConfig(name="country", type="str")},
            max_rows_default=10,
        ),
        "pinned_down": QueryConfig(
            sql="SELECT * FROM customers",
            params={},
            max_rows_default=10,
            connection="prod",
        ),
    }
    result = verify_queries(queries, targets, registry, reachable)

    # Reachable query gets a real verdict.
    assert result["reachable_one.sql"]["ok"] is True
    assert result["reachable_one.sql"]["value"] == "EXPLAIN ok"

    # Pinned-to-down query is skipped, naming the connection; not blanked.
    skip = result["pinned_down.sql"]
    assert skip.get("warn") is True
    assert "prod" in skip["value"]
    assert "skipped" in skip["value"]
    # Static checks still run for the skipped query.
    assert result["pinned_down.params"]["ok"] is True
    assert result["pinned_down.max_rows_default"]["ok"] is True

    # Skip alone does not flip overall_ok.
    assert result["overall_ok"] is True


def test_verify_queries_two_databases_each_explained_against_own_target(
    sqlite_backend: SQLiteBackend,
) -> None:
    """Two databases on one connection, a query pinned to each → both EXPLAINed."""
    sales = ResolvedTarget(
        connection="prod",
        database="sales",
        config=ConnectionConfig(backend="sqlite", path=":memory:"),
        backend_name="sqlite",
        is_default=True,
    )
    hr = ResolvedTarget(
        connection="prod",
        database="hr",
        config=ConnectionConfig(backend="sqlite", path=":memory:"),
        backend_name="sqlite",
        is_default=False,
    )
    targets = ResolvedTargets(
        targets=[sales, hr],
        default=sales,
        file_default_connection="prod",
    )
    registry = StubRegistry(sqlite_backend)
    reachable = {("prod", "sales"): True, ("prod", "hr"): True}

    queries = {
        "on_sales": QueryConfig(
            sql="SELECT * FROM customers",
            params={},
            max_rows_default=10,
            database="sales",
        ),
        "on_hr": QueryConfig(
            sql="SELECT * FROM customers",
            params={},
            max_rows_default=10,
            database="hr",
        ),
    }
    result = verify_queries(queries, targets, registry, reachable)

    assert result["on_sales.sql"]["ok"] is True
    assert result["on_hr.sql"]["ok"] is True
    assert result["overall_ok"] is True


# ---------------------------------------------------------------------------
# Per-variant read_only rows
# ---------------------------------------------------------------------------


def test_read_only_row_passes_for_clean_select(
    sqlite_targets: ResolvedTargets,
    sqlite_registry: BackendRegistry,
    all_reachable: dict[tuple[str, str], bool],
) -> None:
    """A clean SELECT gets one ``read_only[sqlite]`` row with ok=True."""
    queries = {
        "clean": QueryConfig(
            sql="SELECT * FROM customers",
            params={},
            max_rows_default=10,
        ),
    }
    result = verify_queries(queries, sqlite_targets, sqlite_registry, all_reachable)

    row = result["clean.read_only[sqlite]"]
    assert row["ok"] is True
    assert row["value"] == "read-only"
    assert row["error"] == ""
    assert result["overall_ok"] is True


def test_read_only_row_fails_for_delete(
    sqlite_targets: ResolvedTargets,
    sqlite_registry: BackendRegistry,
    all_reachable: dict[tuple[str, str], bool],
) -> None:
    """A DELETE query fails its read_only row and carries the rejection text."""
    queries = {
        "wipe": QueryConfig(
            sql="DELETE FROM customers",
            params={},
            max_rows_default=10,
        ),
    }
    result = verify_queries(queries, sqlite_targets, sqlite_registry, all_reachable)

    row = result["wipe.read_only[sqlite]"]
    assert row["ok"] is False
    assert row["value"] == "failed"
    assert row["error"]
    assert result["overall_ok"] is False


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 'abc",
        "SELECT 1 /* unterminated",
        "SELECT [abc",
    ],
)
def test_read_only_row_fails_for_untokenizable_sql(
    sqlite_targets: ResolvedTargets,
    sqlite_registry: BackendRegistry,
    all_reachable: dict[tuple[str, str], bool],
    sql: str,
) -> None:
    """An unterminated literal, comment or bracket is a row, not a traceback.

    sqlglot raises ``TokenError`` for these -- a sibling of ``ParseError``, not
    a subclass -- so a narrower catch would kill ``verify`` outright.
    """
    queries = {
        "broken": QueryConfig(sql=sql, params={}, max_rows_default=10),
    }
    result = verify_queries(queries, sqlite_targets, sqlite_registry, all_reachable)

    row = result["broken.read_only[sqlite]"]
    assert row["ok"] is False
    assert row["value"] == "failed"
    assert "could not be parsed as sqlite" in row["error"]
    assert "\n" not in row["error"]
    assert result["overall_ok"] is False


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM customers",  # rejected by the AST gate
        "SELECT * FROMX badtable",  # rejected by the fail-closed parse contract
        "SELECT 'abc",  # rejected by the fail-closed parse contract (TokenError)
    ],
)
def test_sql_row_skipped_when_query_is_not_read_only(
    sqlite_backend: SQLiteBackend,
    sqlite_targets: ResolvedTargets,
    all_reachable: dict[tuple[str, str], bool],
    sql: str,
) -> None:
    """A rejected query is never EXPLAINed; its ``.sql`` row is ``(skipped)``.

    EXPLAINing it would send the database operator the very SQL the gate
    refuses and report the database's complaint about it, which is actively
    misleading about why the query is bad.
    """
    explain = MagicMock(wraps=sqlite_backend.explain)
    sqlite_backend.explain = explain  # type: ignore[method-assign]
    queries = {"wipe": QueryConfig(sql=sql, params={}, max_rows_default=10)}

    result = verify_queries(
        queries, sqlite_targets, StubRegistry(sqlite_backend), all_reachable
    )

    assert explain.call_count == 0
    row = result["wipe.sql"]
    assert row["value"] == "(skipped)"
    assert row.get("warn") is True
    assert row["ok"] is True
    # The read_only row, not the skipped .sql row, carries the reason and the
    # failing exit code.
    assert result["wipe.read_only[sqlite]"]["ok"] is False
    assert result["overall_ok"] is False


def test_sql_row_explained_when_query_is_read_only(
    sqlite_backend: SQLiteBackend,
    sqlite_targets: ResolvedTargets,
    all_reachable: dict[tuple[str, str], bool],
) -> None:
    """A read-only query still reaches EXPLAIN -- the skip is not blanket."""
    explain = MagicMock(wraps=sqlite_backend.explain)
    sqlite_backend.explain = explain  # type: ignore[method-assign]
    queries = {
        "fine": QueryConfig(
            sql="SELECT * FROM customers", params={}, max_rows_default=10
        )
    }

    result = verify_queries(
        queries, sqlite_targets, StubRegistry(sqlite_backend), all_reachable
    )

    assert explain.call_count == 1
    assert result["fine.sql"]["value"] == "EXPLAIN ok"
    assert result["overall_ok"] is True


def test_read_only_row_per_backend_variant(
    sqlite_targets: ResolvedTargets,
    sqlite_registry: BackendRegistry,
    all_reachable: dict[tuple[str, str], bool],
) -> None:
    """A clean pinned SELECT plus a DELETE mssql override → one row each verdict."""
    queries = {
        "mixed": QueryConfig(
            sql="SELECT * FROM customers",
            params={},
            max_rows_default=10,
            backends={"mssql": BackendQueryConfig(sql="DELETE FROM customers")},
        ),
    }
    result = verify_queries(queries, sqlite_targets, sqlite_registry, all_reachable)

    assert result["mixed.read_only[sqlite]"]["ok"] is True
    assert result["mixed.read_only[mssql]"]["ok"] is False
    assert result["mixed.read_only[mssql]"]["error"]
    assert result["overall_ok"] is False


def test_read_only_row_warns_for_unmappable_backend(
    sqlite_targets: ResolvedTargets,
    sqlite_registry: BackendRegistry,
    all_reachable: dict[tuple[str, str], bool],
) -> None:
    """A ``backends.postgresql`` key is dead config: a warn row, not a failure."""
    queries = {
        "odd": QueryConfig(
            sql="SELECT * FROM customers",
            params={},
            max_rows_default=10,
            backends={"postgresql": BackendQueryConfig(sql="SELECT 1")},
        ),
    }
    result = verify_queries(queries, sqlite_targets, sqlite_registry, all_reachable)

    row = result["odd.read_only[postgresql]"]
    assert row["warn"] is True
    assert row["value"] == "(unknown backend)"
    assert "postgresql" in row["error"]
    assert result["overall_ok"] is True


def test_read_only_row_unsuffixed_when_pin_unresolvable(
    sqlite_targets: ResolvedTargets,
    sqlite_registry: BackendRegistry,
    all_reachable: dict[tuple[str, str], bool],
) -> None:
    """An unresolvable pin yields exactly one un-suffixed ``read_only`` row."""
    queries = {
        "lost": QueryConfig(
            sql="SELECT * FROM customers",
            params={},
            max_rows_default=10,
            connection="nope",
        ),
    }
    result = verify_queries(queries, sqlite_targets, sqlite_registry, all_reachable)

    read_only_keys = [k for k in result if ".read_only" in k]
    assert read_only_keys == ["lost.read_only"]
    row = result["lost.read_only"]
    assert row["ok"] is False
    assert row["value"] == "(skipped)"
    assert row["error"]
    assert result["lost.params"]["value"] == "(skipped)"
    assert result["overall_ok"] is False


def test_read_only_rows_sit_between_sql_and_params(
    sqlite_targets: ResolvedTargets,
    sqlite_registry: BackendRegistry,
    all_reachable: dict[tuple[str, str], bool],
) -> None:
    """Row order is ``.sql``, the read_only rows, then ``.params``."""
    queries = {
        "ordered": QueryConfig(
            sql="SELECT * FROM customers",
            params={},
            max_rows_default=10,
            backends={"mssql": BackendQueryConfig(sql="SELECT * FROM customers")},
        ),
    }
    result = verify_one_query(
        "ordered",
        queries["ordered"],
        sqlite_targets,
        sqlite_registry,
        all_reachable,
    )

    assert list(result.keys()) == [
        "ordered.sql",
        "ordered.read_only[sqlite]",
        "ordered.read_only[mssql]",
        "ordered.params",
        "ordered.max_rows_default",
        "ordered.max_rows_hard",
    ]
