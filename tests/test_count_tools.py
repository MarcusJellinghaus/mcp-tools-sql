"""Tests for the CountTools class and ``count_records`` tool."""

from __future__ import annotations

from pathlib import Path
from typing import Any, get_args
from unittest.mock import MagicMock

import pytest
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import create_connected_server_and_client_session

from mcp_tools_sql.backends.sqlite import SQLiteBackend
from mcp_tools_sql.config.models import ConnectionConfig, ResolvedTargets
from mcp_tools_sql.count_tools import CountTools
from mcp_tools_sql.query_helpers import build_target_params
from tests.target_helpers import RecordingRegistry, make_target, single_target


def _sqlite_backend(db_path: Path) -> SQLiteBackend:
    """Return a connected SQLite backend for the given database path."""
    backend = SQLiteBackend(ConnectionConfig(backend="sqlite", path=str(db_path)))
    backend.connect()
    return backend


async def _call_count(
    client: Any,
    sql: str,
    params: dict[str, Any] | None = None,
    *,
    connection: str | None = None,
    database: str | None = None,
) -> str:
    """Call ``count_records`` via the MCP client and return the text content."""
    args: dict[str, Any] = {"sql": sql}
    if params is not None:
        args["params"] = params
    if connection is not None:
        args["connection"] = connection
    if database is not None:
        args["database"] = database
    result = await client.call_tool("count_records", args)
    return result.content[0].text  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------
# SQLite end-to-end counts (the real placeholder round-trip verification)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_count_all_customers(sqlite_db: Path) -> None:
    """``SELECT * FROM customers`` counts the seeded two rows."""
    backend = _sqlite_backend(sqlite_db)
    mcp = FastMCP("test-count-customers")
    CountTools(*single_target(backend)).register(mcp)
    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        text = await _call_count(client, "SELECT * FROM customers")
    assert text == "2"


@pytest.mark.asyncio
async def test_count_all_orders(sqlite_db: Path) -> None:
    """``SELECT * FROM orders`` counts the seeded three rows."""
    backend = _sqlite_backend(sqlite_db)
    mcp = FastMCP("test-count-orders")
    CountTools(*single_target(backend)).register(mcp)
    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        text = await _call_count(client, "SELECT * FROM orders")
    assert text == "3"


@pytest.mark.asyncio
async def test_count_with_where_filter(sqlite_db: Path) -> None:
    """A ``WHERE`` filter narrows the count to the matching subset."""
    backend = _sqlite_backend(sqlite_db)
    mcp = FastMCP("test-count-where")
    CountTools(*single_target(backend)).register(mcp)
    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        text = await _call_count(
            client, "SELECT * FROM orders WHERE status = 'pending'"
        )
    assert text == "2"


@pytest.mark.asyncio
async def test_count_with_duplicate_output_columns(sqlite_db: Path) -> None:
    """Duplicate inner output columns still count via the COUNT(*) wrapper.

    ``SELECT id, id FROM customers`` produces a derived table with duplicate
    column names; the ``SELECT COUNT(*) FROM (<sql>) AS count_sub`` wrapper
    does not reference them, so the count succeeds.
    """
    backend = _sqlite_backend(sqlite_db)
    mcp = FastMCP("test-count-dup-cols")
    CountTools(*single_target(backend)).register(mcp)
    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        text = await _call_count(client, "SELECT id, id FROM customers")
    assert text == "2"


@pytest.mark.asyncio
async def test_count_with_named_placeholder(sqlite_db: Path) -> None:
    """A ``:name`` placeholder round-trips through the count wrapper."""
    backend = _sqlite_backend(sqlite_db)
    mcp = FastMCP("test-count-named-param")
    CountTools(*single_target(backend)).register(mcp)
    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        text = await _call_count(
            client,
            "SELECT * FROM orders WHERE status = :s",
            params={"s": "pending"},
        )
    assert text == "2"


# ---------------------------------------------------------------------------
# Read-only gate rejections (writes are rejected before any execution)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "write_sql",
    [
        "UPDATE customers SET name = 'X' WHERE id = 1",
        "INSERT INTO customers VALUES (3, 'Bank C', 'Spain')",
        "DELETE FROM customers WHERE id = 1",
        "DROP TABLE customers",
    ],
)
async def test_write_statements_rejected_and_not_executed(
    sqlite_db: Path, write_sql: str
) -> None:
    """Write statements are rejected as not-read-only and never executed."""
    backend = _sqlite_backend(sqlite_db)
    mcp = FastMCP("test-count-write-reject")
    CountTools(*single_target(backend)).register(mcp)
    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        text = await _call_count(client, write_sql)
    assert text.startswith("Not read-only.")
    # The customers table is untouched: still two rows, still named "Bank A".
    rows = backend.execute_query("SELECT name FROM customers WHERE id = 1")
    assert rows == [{"name": "Bank A"}]
    assert backend.execute_query("SELECT COUNT(*) AS n FROM customers") == [{"n": 2}]


# ---------------------------------------------------------------------------
# Pre-flight parity with validate_sql
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_preflight_empty_sql(sqlite_db: Path) -> None:
    """Empty SQL is rejected before any DB round-trip."""
    backend = _sqlite_backend(sqlite_db)
    mcp = FastMCP("test-count-empty")
    CountTools(*single_target(backend)).register(mcp)
    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        text = await _call_count(client, "")
    assert text == "Invalid SQL. ValidationError: empty SQL"


@pytest.mark.asyncio
async def test_preflight_multi_statement(sqlite_db: Path) -> None:
    """Multi-statement SQL is rejected without a DB round-trip."""
    backend = _sqlite_backend(sqlite_db)
    mcp = FastMCP("test-count-multi")
    CountTools(*single_target(backend)).register(mcp)
    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        text = await _call_count(client, "SELECT 1; SELECT 2")
    assert text == "Invalid SQL. ValidationError: multiple statements not supported"


@pytest.mark.asyncio
async def test_preflight_missing_param(sqlite_db: Path) -> None:
    """A missing ``:name`` parameter is rejected at pre-flight."""
    backend = _sqlite_backend(sqlite_db)
    mcp = FastMCP("test-count-missing-param")
    CountTools(*single_target(backend)).register(mcp)
    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        text = await _call_count(client, "SELECT * FROM orders WHERE status = :s")
    assert text == "Invalid parameters. ValidationError: missing parameter: s"


@pytest.mark.asyncio
async def test_preflight_unparseable_fail_closed(sqlite_db: Path) -> None:
    """Unparseable SQL is rejected (fail-closed) before any execution."""
    backend = _sqlite_backend(sqlite_db)
    mcp = FastMCP("test-count-fail-closed")
    CountTools(*single_target(backend)).register(mcp)
    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        text = await _call_count(client, "SELECT FROM WHERE")
    assert text.startswith("Invalid SQL. ParseError: ")


# ---------------------------------------------------------------------------
# Deterministic MSSQL leading-WITH handling (MagicMock backend, no real DB)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mssql_leading_cte_rejected_without_execution() -> None:
    """A T-SQL leading ``WITH`` CTE is rejected before ``execute_readonly_query``."""
    backend = MagicMock()
    mcp = FastMCP("test-count-mssql-cte")
    CountTools(*single_target(backend, backend_name="mssql")).register(mcp)
    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        text = await _call_count(client, "WITH x AS (SELECT 1) SELECT * FROM x")
    assert text == (
        "CTE (WITH) queries can't be counted on SQL Server — "
        "the count wrapper doesn't support them."
    )
    backend.execute_readonly_query.assert_not_called()


@pytest.mark.asyncio
async def test_mssql_with_nolock_hint_not_false_positived() -> None:
    """A T-SQL ``WITH (NOLOCK)`` table hint is NOT treated as a leading CTE.

    The hint is modeled by sqlglot on the table node, not the statement-level
    ``with`` arg, so the leading-CTE gate must let it through to
    ``execute_readonly_query``.
    """
    backend = MagicMock()
    backend.execute_readonly_query.return_value = [{"row_count": 7}]
    mcp = FastMCP("test-count-mssql-nolock")
    CountTools(*single_target(backend, backend_name="mssql")).register(mcp)
    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        text = await _call_count(client, "SELECT * FROM t WITH (NOLOCK)")
    assert text != (
        "CTE (WITH) queries can't be counted on SQL Server — "
        "the count wrapper doesn't support them."
    )
    assert text == "7"
    backend.execute_readonly_query.assert_called_once()


@pytest.mark.asyncio
async def test_mssql_select_into_rejected_without_execution() -> None:
    """A T-SQL ``SELECT ... INTO`` materialises a table, so it is rejected."""
    backend = MagicMock()
    mcp = FastMCP("test-count-mssql-into")
    CountTools(*single_target(backend, backend_name="mssql")).register(mcp)
    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        text = await _call_count(client, "SELECT * INTO new_t FROM t")
    assert text.startswith("Not read-only.")
    assert "SELECT ... INTO" in text
    backend.execute_readonly_query.assert_not_called()


# ---------------------------------------------------------------------------
# Multi-target: per-call backend + dialect resolution (Step 12)
# ---------------------------------------------------------------------------


def _multi_targets() -> ResolvedTargets:
    """Two connections: ``lite`` (sqlite) default + ``sql`` (mssql/tsql).

    ``lite`` → ``main`` (sqlite); ``sql`` → ``hr`` (mssql). The differing
    backends let a test prove that ``count_records`` resolves the sqlglot
    dialect *per call* from the pinned target.
    """
    t_lite = make_target("lite", "main", is_default=True, default_database="main")
    t_sql = make_target("sql", "hr", default_database="hr", backend_name="mssql")
    return ResolvedTargets(
        targets=[t_lite, t_sql], default=t_lite, file_default_connection="lite"
    )


def _literal_members(annotation: Any) -> set[str]:
    """Extract the ``Literal`` members from an ``Annotated[...]`` param annotation.

    Returns:
        The set of string members declared on the (possibly ``Optional``)
        ``Literal`` inside the annotation.
    """
    inner = get_args(annotation)[0]  # unwrap Annotated -> Literal | Optional[Literal]
    literal = inner
    nested = get_args(inner)
    if nested and get_args(nested[0]):  # Optional[Literal[...]]
        literal = nested[0]
    return set(get_args(literal))


def test_count_target_params_database_enum_omits_star() -> None:
    """``build_target_params(star=False)`` omits ``*``; ``star=True`` keeps it.

    ``count_records`` has no fan-out, so its ``database`` enum must never carry
    the ``*`` sentinel — while the shared flag still yields it for the
    ``schema_tools`` fan-out caller.
    """
    targets = _multi_targets()

    pinned = {p.name: p for p in build_target_params(targets, star=False)}
    assert "*" not in _literal_members(pinned["database"].annotation)

    fanned = {p.name: p for p in build_target_params(targets, star=True)}
    assert "*" in _literal_members(fanned["database"].annotation)


@pytest.mark.asyncio
async def test_multi_install_exposes_selector_params(sqlite_db: Path) -> None:
    """A multi-target install surfaces connection/database enums on count_records."""
    backend = _sqlite_backend(sqlite_db)
    targets = _multi_targets()
    registry = RecordingRegistry({("lite", "main"): backend, ("sql", "hr"): backend})
    mcp = FastMCP("test-count-multi-schema")
    CountTools(registry, targets).register(mcp)

    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        result = await client.list_tools()
        tool = next(t for t in result.tools if t.name == "count_records")
        props = tool.inputSchema["properties"]
        assert "connection" in props
        assert "database" in props


@pytest.mark.asyncio
async def test_multi_per_call_dialect_resolved_from_target(sqlite_db: Path) -> None:
    """A leading CTE is rejected only under the pinned tsql target's dialect.

    Pinned to the ``sql`` (mssql/tsql) target the CTE is rejected before any
    execution; pinned to the ``lite`` (sqlite) target the same query counts
    normally. Same install, two dialects — proving per-call resolution. The
    mssql call also records the ``(sql, hr)`` target lookup.
    """
    backend = _sqlite_backend(sqlite_db)
    targets = _multi_targets()
    registry = RecordingRegistry({("lite", "main"): backend, ("sql", "hr"): backend})
    mcp = FastMCP("test-count-multi-dialect")
    CountTools(registry, targets).register(mcp)

    cte_sql = "WITH x AS (SELECT 1 AS n) SELECT * FROM x"
    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        tsql_verdict = await _call_count(
            client, cte_sql, connection="sql", database="hr"
        )
        sqlite_count = await _call_count(client, cte_sql, connection="lite")

    assert tsql_verdict == (
        "CTE (WITH) queries can't be counted on SQL Server — "
        "the count wrapper doesn't support them."
    )
    assert sqlite_count == "1"
    assert registry.calls[0].connection == "sql"
    assert registry.calls[0].database == "hr"


@pytest.mark.asyncio
async def test_multi_cross_connection_mismatch_returns_verdict(
    sqlite_db: Path,
) -> None:
    """A ``(lite, hr)`` mismatch returns the friendly verdict, hits no backend."""
    backend = _sqlite_backend(sqlite_db)
    targets = _multi_targets()
    registry = RecordingRegistry({("lite", "main"): backend, ("sql", "hr"): backend})
    mcp = FastMCP("test-count-multi-mismatch")
    CountTools(registry, targets).register(mcp)

    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        text = await _call_count(
            client, "SELECT * FROM customers", connection="lite", database="hr"
        )

    assert "lite" in text
    assert "hr" in text
    assert "main" in text  # lists the available databases
    assert registry.calls == []  # resolve failed before any backend lookup


@pytest.mark.asyncio
async def test_multi_count_binds_selected_target(sqlite_db: Path) -> None:
    """`connection='lite'` resolves the sqlite target and counts the rows."""
    backend = _sqlite_backend(sqlite_db)
    targets = _multi_targets()
    registry = RecordingRegistry({("lite", "main"): backend, ("sql", "hr"): backend})
    mcp = FastMCP("test-count-multi-select")
    CountTools(registry, targets).register(mcp)

    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        text = await _call_count(client, "SELECT * FROM customers", connection="lite")

    assert text == "2"
    assert registry.calls[-1].connection == "lite"
    assert registry.calls[-1].database == "main"
