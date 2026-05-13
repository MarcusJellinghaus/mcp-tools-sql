"""Tests for the QueryTools class."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import create_connected_server_and_client_session

from mcp_tools_sql.backends.sqlite import SQLiteBackend
from mcp_tools_sql.config.models import (
    BackendQueryConfig,
    ConnectionConfig,
    QueryConfig,
    QueryParamConfig,
)
from mcp_tools_sql.query_helpers import extract_sql_params
from mcp_tools_sql.query_tools import QueryTools


def test_extract_sql_params_skips_string_literal() -> None:
    """Delegation guarantee: placeholders inside string literals are ignored."""
    assert extract_sql_params("SELECT ':foo' AS x WHERE id = :bar") == {"bar"}


def _sqlite_backend(db_path: Path) -> SQLiteBackend:
    """Return a connected SQLite backend for the given database path."""
    backend = SQLiteBackend(ConnectionConfig(backend="sqlite", path=str(db_path)))
    backend.connect()
    return backend


# ---------------------------------------------------------------------------
# Empty queries / name validation / prefix
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_queries_is_noop(sqlite_db: Path) -> None:
    """QueryTools with no queries registers zero tools (no error)."""
    backend = _sqlite_backend(sqlite_db)
    mcp = FastMCP("test-empty-queries")
    QueryTools(backend, {}, "sqlite").register(mcp)

    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        result = await client.list_tools()
        assert result.tools == []


@pytest.mark.asyncio
async def test_tool_name_is_prefixed(sqlite_db: Path) -> None:
    """Configured query 'customers' registers as 'query_customers'."""
    backend = _sqlite_backend(sqlite_db)
    queries = {
        "customers": QueryConfig(
            description="List customers",
            sql="SELECT * FROM customers",
            backends={"sqlite": BackendQueryConfig(sql="SELECT * FROM customers")},
        )
    }
    mcp = FastMCP("test-prefix")
    QueryTools(backend, queries, "sqlite").register(mcp)

    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        result = await client.list_tools()
        names = {t.name for t in result.tools}
        assert "query_customers" in names
        assert "customers" not in names


def test_invalid_query_name_raises(sqlite_db: Path) -> None:
    """Invalid query name raises ValueError mentioning the offending name."""
    backend = _sqlite_backend(sqlite_db)
    queries = {
        "123-bad": QueryConfig(
            description="Bad name",
            sql="SELECT 1",
        )
    }
    mcp = FastMCP("test-invalid")
    with pytest.raises(ValueError, match="123-bad"):
        QueryTools(backend, queries, "sqlite").register(mcp)


# ---------------------------------------------------------------------------
# JSON schema generation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_json_schema_generation(sqlite_db: Path) -> None:
    """Generated input schema has correct types, required entries, and max_rows."""
    backend = _sqlite_backend(sqlite_db)
    queries = {
        "orders": QueryConfig(
            description="Search orders",
            sql=(
                "SELECT * FROM orders WHERE customer_id = :customer_id "
                "AND status = :status"
            ),
            params={
                "customer_id": QueryParamConfig(
                    name="customer_id",
                    type="int",
                    description="Customer ID",
                ),
                "status": QueryParamConfig(
                    name="status",
                    type="str",
                    description="Order status",
                ),
                "min_total": QueryParamConfig(
                    name="min_total",
                    type="float",
                    description="Minimum total",
                    required=False,
                ),
            },
            backends={
                "sqlite": BackendQueryConfig(
                    sql=(
                        "SELECT * FROM orders WHERE customer_id = :customer_id "
                        "AND status = :status"
                    )
                )
            },
        )
    }
    mcp = FastMCP("test-schema")
    QueryTools(backend, queries, "sqlite").register(mcp)

    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        result = await client.list_tools()
        tool = next(t for t in result.tools if t.name == "query_orders")
        schema = tool.inputSchema
        props = schema["properties"]
        assert props["customer_id"]["type"] == "integer"
        assert props["status"]["type"] == "string"
        assert "min_total" in props
        assert "max_rows" in props

        required = schema.get("required", [])
        assert "customer_id" in required
        assert "status" in required
        assert "min_total" not in required
        assert "max_rows" not in required


# ---------------------------------------------------------------------------
# SQLite integration: register + call
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_and_call_via_mcp(sqlite_db: Path) -> None:
    """Round-trip: register a query tool and call it via MCP, verifying output."""
    backend = _sqlite_backend(sqlite_db)
    queries = {
        "customers_by_country": QueryConfig(
            description="Find customers by country",
            sql="SELECT id, name FROM customers WHERE country = :country",
            params={
                "country": QueryParamConfig(name="country", type="str"),
            },
            backends={
                "sqlite": BackendQueryConfig(
                    sql="SELECT id, name FROM customers WHERE country = :country"
                )
            },
        )
    }
    mcp = FastMCP("test-call")
    QueryTools(backend, queries, "sqlite").register(mcp)

    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        result = await client.call_tool(
            "query_customers_by_country", {"country": "Germany"}
        )
        text = result.content[0].text  # type: ignore[union-attr]
        assert "Bank A" in text
        assert "Bank B" not in text


# ---------------------------------------------------------------------------
# Parameterized queries (int / string / optional)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_parameterized_int_string_optional(sqlite_db: Path) -> None:
    """Each declared parameter type binds correctly when invoked via MCP."""
    backend = _sqlite_backend(sqlite_db)
    queries = {
        "orders_search": QueryConfig(
            description="Search orders by id/status",
            sql=(
                "SELECT id, status, total FROM orders WHERE customer_id = "
                ":customer_id AND status = :status"
            ),
            params={
                "customer_id": QueryParamConfig(name="customer_id", type="int"),
                "status": QueryParamConfig(name="status", type="str"),
                "min_total": QueryParamConfig(
                    name="min_total",
                    type="float",
                    required=False,
                ),
            },
            backends={
                "sqlite": BackendQueryConfig(
                    sql=(
                        "SELECT id, status, total FROM orders WHERE customer_id "
                        "= :customer_id AND status = :status"
                    )
                )
            },
        )
    }
    mcp = FastMCP("test-params")
    QueryTools(backend, queries, "sqlite").register(mcp)

    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        result = await client.call_tool(
            "query_orders_search",
            {"customer_id": 1, "status": "pending"},
        )
        text = result.content[0].text  # type: ignore[union-attr]
        assert "pending" in text
        assert "1000" in text
        assert "shipped" not in text


# ---------------------------------------------------------------------------
# max_rows truncation behavior
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_max_rows_truncation_hint(sqlite_db: Path) -> None:
    """Truncation appends the query-tools specific hint text."""
    backend = _sqlite_backend(sqlite_db)
    queries = {
        "orders": QueryConfig(
            description="All orders",
            sql="SELECT id FROM orders",
            backends={"sqlite": BackendQueryConfig(sql="SELECT id FROM orders")},
            max_rows_default=2,
            max_rows_hard=10,
        )
    }
    mcp = FastMCP("test-truncate")
    QueryTools(backend, queries, "sqlite").register(mcp)

    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        result = await client.call_tool("query_orders", {})
        text = result.content[0].text  # type: ignore[union-attr]
        assert "Showing 2 of 3 rows" in text
        assert "Refine your query parameters or increase max_rows." in text


# ---------------------------------------------------------------------------
# max_rows_hard clamp
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_max_rows_hard_clamp(sqlite_db: Path) -> None:
    """Requested max_rows above hard limit is clamped and a note appears."""
    backend = _sqlite_backend(sqlite_db)
    queries = {
        "orders": QueryConfig(
            description="All orders",
            sql="SELECT id FROM orders",
            backends={"sqlite": BackendQueryConfig(sql="SELECT id FROM orders")},
            max_rows_default=5,
            max_rows_hard=10,
        )
    }
    mcp = FastMCP("test-clamp")
    QueryTools(backend, queries, "sqlite").register(mcp)

    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        result = await client.call_tool("query_orders", {"max_rows": 500})
        text = result.content[0].text  # type: ignore[union-attr]
        assert "Requested max_rows=500 exceeds hard limit 10" in text
        assert "capped at 10" in text


# ---------------------------------------------------------------------------
# SQL injection prevention
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_params_passed_as_dict_not_interpolated(
    sqlite_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Parameters reach the backend as a dict, not interpolated into the SQL string."""
    backend = _sqlite_backend(sqlite_db)
    captured: dict[str, Any] = {}
    original = backend.execute_query

    def spy(sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        captured["sql"] = sql
        captured["params"] = params
        return original(sql, params)

    monkeypatch.setattr(backend, "execute_query", spy)

    queries = {
        "by_country": QueryConfig(
            description="By country",
            sql="SELECT id FROM customers WHERE country = :country",
            params={"country": QueryParamConfig(name="country", type="str")},
            backends={
                "sqlite": BackendQueryConfig(
                    sql="SELECT id FROM customers WHERE country = :country"
                )
            },
        )
    }
    mcp = FastMCP("test-injection")
    QueryTools(backend, queries, "sqlite").register(mcp)

    payload = "Germany'; DROP TABLE customers; --"
    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        await client.call_tool("query_by_country", {"country": payload})

    assert isinstance(captured["params"], dict)
    assert captured["params"] == {"country": payload}
    assert payload not in captured["sql"]
    assert ":country" in captured["sql"]


# ---------------------------------------------------------------------------
# Missing required param surfaces an MCP error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_required_param_errors(sqlite_db: Path) -> None:
    """Calling without a required parameter yields a clear MCP error."""
    backend = _sqlite_backend(sqlite_db)
    queries = {
        "by_country": QueryConfig(
            description="By country",
            sql="SELECT id FROM customers WHERE country = :country",
            params={"country": QueryParamConfig(name="country", type="str")},
            backends={
                "sqlite": BackendQueryConfig(
                    sql="SELECT id FROM customers WHERE country = :country"
                )
            },
        )
    }
    mcp = FastMCP("test-missing")
    QueryTools(backend, queries, "sqlite").register(mcp)

    async with create_connected_server_and_client_session(mcp) as client:
        result = await client.call_tool("query_by_country", {})
        assert result.isError


# ---------------------------------------------------------------------------
# Per-backend SQL override applied
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_per_backend_sql_override_applied(sqlite_db: Path) -> None:
    """When backends.sqlite is set, the override is what executes."""
    backend = _sqlite_backend(sqlite_db)
    queries = {
        "all_names": QueryConfig(
            description="Override test",
            sql="SELECT 'default-only' AS name",
            backends={
                "sqlite": BackendQueryConfig(sql="SELECT 'sqlite-override' AS name")
            },
        )
    }
    mcp = FastMCP("test-override")
    QueryTools(backend, queries, "sqlite").register(mcp)

    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        result = await client.call_tool("query_all_names", {})
        text = result.content[0].text  # type: ignore[union-attr]
        assert "sqlite-override" in text
        assert "default-only" not in text


# ---------------------------------------------------------------------------
# Filter parameter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_filter_parameter(sqlite_db: Path) -> None:
    """Configured filter_column exposes a <col>_filter that narrows rows."""
    backend = _sqlite_backend(sqlite_db)
    queries = {
        "all_customers": QueryConfig(
            description="All customers",
            sql="SELECT id, name FROM customers",
            backends={
                "sqlite": BackendQueryConfig(sql="SELECT id, name FROM customers")
            },
            filter_column="name",
        )
    }
    mcp = FastMCP("test-filter")
    QueryTools(backend, queries, "sqlite").register(mcp)

    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        result = await client.call_tool(
            "query_all_customers", {"name_filter": "Bank A"}
        )
        text = result.content[0].text  # type: ignore[union-attr]
        assert "Bank A" in text
        assert "Bank B" not in text


# ---------------------------------------------------------------------------
# Datetime parameter binding
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_query_tool_binds_datetime_param(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ISO 8601 string from MCP caller is parsed to datetime and passed through."""
    db_path = tmp_path / "events.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE events (id INTEGER PRIMARY KEY, occurred_at TEXT)")
    conn.execute("INSERT INTO events VALUES (1, '2025-01-01T00:00:00')")
    conn.commit()
    conn.close()

    backend = _sqlite_backend(db_path)
    captured: dict[str, Any] = {}
    original = backend.execute_query

    def spy(sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        captured["params"] = params
        return original(sql, params)

    monkeypatch.setattr(backend, "execute_query", spy)

    queries = {
        "events_since": QueryConfig(
            description="Events since",
            sql="SELECT id FROM events WHERE occurred_at >= :since",
            params={"since": QueryParamConfig(name="since", type="datetime")},
            backends={
                "sqlite": BackendQueryConfig(
                    sql="SELECT id FROM events WHERE occurred_at >= :since"
                )
            },
        )
    }
    mcp = FastMCP("test-datetime")
    QueryTools(backend, queries, "sqlite").register(mcp)

    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        await client.call_tool("query_events_since", {"since": "2024-12-31T00:00:00"})

    assert isinstance(captured["params"], dict)
    assert isinstance(captured["params"]["since"], datetime)
    assert captured["params"]["since"] == datetime(2024, 12, 31, 0, 0, 0)
