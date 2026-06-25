"""Tests for the CountTools class and ``count_records`` tool."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import create_connected_server_and_client_session

from mcp_tools_sql.backends.sqlite import SQLiteBackend
from mcp_tools_sql.config.models import ConnectionConfig
from mcp_tools_sql.count_tools import CountTools


def _sqlite_backend(db_path: Path) -> SQLiteBackend:
    """Return a connected SQLite backend for the given database path."""
    backend = SQLiteBackend(ConnectionConfig(backend="sqlite", path=str(db_path)))
    backend.connect()
    return backend


async def _call_count(
    client: Any,
    sql: str,
    params: dict[str, Any] | None = None,
) -> str:
    """Call ``count_records`` via the MCP client and return the text content."""
    args: dict[str, Any] = {"sql": sql}
    if params is not None:
        args["params"] = params
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
    CountTools(backend, "sqlite").register(mcp)
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
    CountTools(backend, "sqlite").register(mcp)
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
    CountTools(backend, "sqlite").register(mcp)
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
    CountTools(backend, "sqlite").register(mcp)
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
    CountTools(backend, "sqlite").register(mcp)
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
    CountTools(backend, "sqlite").register(mcp)
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
    CountTools(backend, "sqlite").register(mcp)
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
    CountTools(backend, "sqlite").register(mcp)
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
    CountTools(backend, "sqlite").register(mcp)
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
    CountTools(backend, "sqlite").register(mcp)
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
    CountTools(backend, "mssql").register(mcp)
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
    CountTools(backend, "mssql").register(mcp)
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
    CountTools(backend, "mssql").register(mcp)
    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        text = await _call_count(client, "SELECT * INTO new_t FROM t")
    assert text.startswith("Not read-only.")
    assert "SELECT ... INTO" in text
    backend.execute_readonly_query.assert_not_called()
