"""Tests for schema_tools helper functions and integration tests."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import create_connected_server_and_client_session

from mcp_tools_sql.backends.sqlite import SQLiteBackend
from mcp_tools_sql.config.models import (
    BackendQueryConfig,
    ConnectionConfig,
    QueryConfig,
)
from mcp_tools_sql.schema_tools import SchemaTools, load_default_queries
from mcp_tools_sql.tool_builder import build_tool_fn

# ---------------------------------------------------------------------------
# Helper: create FastMCP with registered builtin tools against a SQLite DB
# ---------------------------------------------------------------------------


def _make_mcp_with_tools(db_path: str) -> FastMCP:
    """Create a FastMCP instance with builtin tools registered against a SQLite DB."""
    config = ConnectionConfig(backend="sqlite", path=db_path)
    backend = SQLiteBackend(config)
    backend.connect()
    mcp = FastMCP("test-schema-tools")
    SchemaTools(backend, "sqlite").register(mcp)
    return mcp


# ---------------------------------------------------------------------------
# MCP protocol integration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestSchemaToolsMcpProtocol:
    """Full-pipeline tests: TOML → config → dynamic function → MCP → SQLite → text."""

    async def test_all_four_tools_discoverable(self, sqlite_db: Path) -> None:
        """list_tools() returns read_schemas, read_tables, read_columns, read_relations."""
        mcp = _make_mcp_with_tools(str(sqlite_db))
        async with create_connected_server_and_client_session(
            mcp, raise_exceptions=True
        ) as client:
            result = await client.list_tools()
            tool_names = {t.name for t in result.tools}
            assert tool_names == {
                "read_schemas",
                "read_tables",
                "read_columns",
                "read_relations",
            }

    async def test_read_schemas(self, sqlite_db: Path) -> None:
        """call_tool('read_schemas') returns formatted table with 'main'."""
        mcp = _make_mcp_with_tools(str(sqlite_db))
        async with create_connected_server_and_client_session(
            mcp, raise_exceptions=True
        ) as client:
            result = await client.call_tool("read_schemas", {})
            text = result.content[0].text  # type: ignore[union-attr]
            assert "main" in text

    async def test_read_tables(self, sqlite_db: Path) -> None:
        """call_tool('read_tables', {schema: 'main'}) returns customers and orders."""
        mcp = _make_mcp_with_tools(str(sqlite_db))
        async with create_connected_server_and_client_session(
            mcp, raise_exceptions=True
        ) as client:
            result = await client.call_tool("read_tables", {"schema": "main"})
            text = result.content[0].text  # type: ignore[union-attr]
            assert "customers" in text
            assert "orders" in text

    async def test_read_columns(self, sqlite_db: Path) -> None:
        """call_tool('read_columns', {schema: 'main', table: 'customers'}) returns column metadata."""
        mcp = _make_mcp_with_tools(str(sqlite_db))
        async with create_connected_server_and_client_session(
            mcp, raise_exceptions=True
        ) as client:
            result = await client.call_tool(
                "read_columns", {"schema": "main", "table": "customers"}
            )
            text = result.content[0].text  # type: ignore[union-attr]
            assert "id" in text
            assert "name" in text
            assert "country" in text

    async def test_read_columns_with_filter(self, sqlite_db: Path) -> None:
        """call_tool('read_columns', {name_filter: 'na*'}) filters by glob."""
        mcp = _make_mcp_with_tools(str(sqlite_db))
        async with create_connected_server_and_client_session(
            mcp, raise_exceptions=True
        ) as client:
            result = await client.call_tool(
                "read_columns",
                {"schema": "main", "table": "customers", "name_filter": "na*"},
            )
            text = result.content[0].text  # type: ignore[union-attr]
            assert "name" in text
            assert "country" not in text

    async def test_read_columns_filter_no_match(self, sqlite_db: Path) -> None:
        """Filter with no matches returns 'No results found.'."""
        mcp = _make_mcp_with_tools(str(sqlite_db))
        async with create_connected_server_and_client_session(
            mcp, raise_exceptions=True
        ) as client:
            result = await client.call_tool(
                "read_columns",
                {"schema": "main", "table": "customers", "name_filter": "zzz*"},
            )
            text = result.content[0].text  # type: ignore[union-attr]
            assert text == "No results found."

    async def test_read_relations(self, sqlite_db: Path) -> None:
        """call_tool('read_relations', {table: 'orders'}) returns FK info."""
        mcp = _make_mcp_with_tools(str(sqlite_db))
        async with create_connected_server_and_client_session(
            mcp, raise_exceptions=True
        ) as client:
            result = await client.call_tool(
                "read_relations", {"schema": "main", "table": "orders"}
            )
            text = result.content[0].text  # type: ignore[union-attr]
            assert "customers" in text
            assert "customer_id" in text

    async def test_read_relations_no_fks(self, sqlite_db: Path) -> None:
        """Table without FKs returns 'No results found.'."""
        mcp = _make_mcp_with_tools(str(sqlite_db))
        async with create_connected_server_and_client_session(
            mcp, raise_exceptions=True
        ) as client:
            result = await client.call_tool(
                "read_relations", {"schema": "main", "table": "customers"}
            )
            text = result.content[0].text  # type: ignore[union-attr]
            assert text == "No results found."


# ---------------------------------------------------------------------------
# Truncation tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestSchemaToolsTruncation:
    """Verify truncation behavior for wide tables."""

    async def test_wide_table_truncation(self, sqlite_wide_db: Path) -> None:
        """read_columns on 150-column table with default max_rows=100 shows truncation message."""
        mcp = _make_mcp_with_tools(str(sqlite_wide_db))
        async with create_connected_server_and_client_session(
            mcp, raise_exceptions=True
        ) as client:
            result = await client.call_tool(
                "read_columns", {"schema": "main", "table": "wide_table"}
            )
            text = result.content[0].text  # type: ignore[union-attr]
            assert "Showing 100 of 150 rows" in text
            assert "Use filter to narrow" in text

    async def test_wide_table_custom_max_rows(self, sqlite_wide_db: Path) -> None:
        """read_columns with max_rows=10 truncates at 10 and shows message."""
        mcp = _make_mcp_with_tools(str(sqlite_wide_db))
        async with create_connected_server_and_client_session(
            mcp, raise_exceptions=True
        ) as client:
            result = await client.call_tool(
                "read_columns",
                {"schema": "main", "table": "wide_table", "max_rows": 10},
            )
            text = result.content[0].text  # type: ignore[union-attr]
            assert "Showing 10 of 150 rows" in text

    async def test_no_truncation_within_limit(self, sqlite_db: Path) -> None:
        """Small table with 3 columns → no truncation message."""
        mcp = _make_mcp_with_tools(str(sqlite_db))
        async with create_connected_server_and_client_session(
            mcp, raise_exceptions=True
        ) as client:
            result = await client.call_tool(
                "read_columns", {"schema": "main", "table": "customers"}
            )
            text = result.content[0].text  # type: ignore[union-attr]
            assert "Showing" not in text
            assert "id" in text


# ---------------------------------------------------------------------------
# Param stripping tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestParamStripping:
    """Verify that params not referenced in backend SQL are stripped."""

    async def test_schema_param_ignored_for_sqlite(self, sqlite_db: Path) -> None:
        """read_tables accepts schema param but SQLite SQL doesn't use it — no error."""
        mcp = _make_mcp_with_tools(str(sqlite_db))
        async with create_connected_server_and_client_session(
            mcp, raise_exceptions=True
        ) as client:
            # SQLite read_tables SQL has no :schema param, but we pass it
            result = await client.call_tool("read_tables", {"schema": "main"})
            text = result.content[0].text  # type: ignore[union-attr]
            assert "customers" in text

    async def test_read_schemas_no_params(self, sqlite_db: Path) -> None:
        """read_schemas has no params in SQLite SQL — works with empty args."""
        mcp = _make_mcp_with_tools(str(sqlite_db))
        async with create_connected_server_and_client_session(
            mcp, raise_exceptions=True
        ) as client:
            result = await client.call_tool("read_schemas", {})
            assert not result.isError


# ---------------------------------------------------------------------------
# Edge case tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestSchemaToolsEdgeCases:
    """Edge case tests for schema tools."""

    async def test_empty_database(self, tmp_path: Path) -> None:
        """read_tables on empty database returns 'No results found.'."""
        db_path = tmp_path / "empty.db"
        import sqlite3

        conn = sqlite3.connect(str(db_path))
        conn.close()

        mcp = _make_mcp_with_tools(str(db_path))
        async with create_connected_server_and_client_session(
            mcp, raise_exceptions=True
        ) as client:
            result = await client.call_tool("read_tables", {"schema": "main"})
            text = result.content[0].text  # type: ignore[union-attr]
            assert text == "No results found."

    async def test_read_columns_nonexistent_table(self, sqlite_db: Path) -> None:
        """read_columns on non-existent table returns 'No results found.'."""
        mcp = _make_mcp_with_tools(str(sqlite_db))
        async with create_connected_server_and_client_session(
            mcp, raise_exceptions=True
        ) as client:
            result = await client.call_tool(
                "read_columns", {"schema": "main", "table": "nonexistent"}
            )
            text = result.content[0].text  # type: ignore[union-attr]
            assert text == "No results found."

    async def test_tool_schemas_have_descriptions(self, sqlite_db: Path) -> None:
        """All tools have non-empty descriptions from TOML config."""
        mcp = _make_mcp_with_tools(str(sqlite_db))
        async with create_connected_server_and_client_session(
            mcp, raise_exceptions=True
        ) as client:
            result = await client.list_tools()
            for tool in result.tools:
                assert tool.description, f"Tool {tool.name} has no description"


# ---------------------------------------------------------------------------
# Per-tool-call logging tests
# ---------------------------------------------------------------------------


@pytest.mark.sqlite_integration
@pytest.mark.asyncio
async def test_builtin_tool_logs_info_line(
    sqlite_db: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Calling a built-in tool emits one INFO log line via log_tool_call."""
    caplog.set_level(logging.INFO, logger="mcp_tools_sql.tool_logging")

    config = ConnectionConfig(backend="sqlite", path=str(sqlite_db))
    backend = SQLiteBackend(config)
    backend.connect()
    queries = load_default_queries()
    fn = build_tool_fn("read_tables", queries["read_tables"], backend, "sqlite")

    await fn()

    info_records = [
        r
        for r in caplog.records
        if r.levelno == logging.INFO
        and "tool=read_tables" in r.getMessage()
        and "duration_ms=" in r.getMessage()
    ]
    assert len(info_records) == 1


# ---------------------------------------------------------------------------
# max_rows hard-limit clamp tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_max_rows_clamped_to_hard_limit(sqlite_wide_db: Path) -> None:
    """Caller passes max_rows above max_rows_hard → clamp + note appended."""
    config = ConnectionConfig(backend="sqlite", path=str(sqlite_wide_db))
    backend = SQLiteBackend(config)
    backend.connect()

    qcfg = QueryConfig(
        sql="SELECT name FROM pragma_table_info(:table)",
        backends={
            "sqlite": BackendQueryConfig(
                sql="SELECT name FROM pragma_table_info(:table)"
            )
        },
        max_rows_default=5,
        max_rows_hard=10,
    )
    fn = build_tool_fn("clamp_test", qcfg, backend, "sqlite")

    text = await fn(table="wide_table", max_rows=500)

    assert "Requested max_rows=500 exceeds hard limit 10" in text
    assert "capped at 10" in text


@pytest.mark.asyncio
async def test_clamp_and_truncation_both_appear(sqlite_wide_db: Path) -> None:
    """When caller exceeds hard limit AND result is still truncated, both notes appear."""
    config = ConnectionConfig(backend="sqlite", path=str(sqlite_wide_db))
    backend = SQLiteBackend(config)
    backend.connect()

    qcfg = QueryConfig(
        sql="SELECT name FROM pragma_table_info(:table)",
        backends={
            "sqlite": BackendQueryConfig(
                sql="SELECT name FROM pragma_table_info(:table)"
            )
        },
        max_rows_default=5,
        max_rows_hard=10,
    )
    fn = build_tool_fn(
        "clamp_trunc_test",
        qcfg,
        backend,
        "sqlite",
        truncation_hint="Use filter to narrow.",
    )

    text = await fn(table="wide_table", max_rows=500)

    assert "Showing 10 of 150 rows" in text
    assert "Use filter to narrow" in text
    assert "Requested max_rows=500 exceeds hard limit 10" in text


# ---------------------------------------------------------------------------
# Truncation-hint plumbing (regression guard)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_truncation_hint_preserved(sqlite_wide_db: Path) -> None:
    """SchemaTools routes ``truncation_hint`` through to format_rows output."""
    mcp = _make_mcp_with_tools(str(sqlite_wide_db))
    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        result = await client.call_tool(
            "read_columns", {"schema": "main", "table": "wide_table"}
        )
        text = result.content[0].text  # type: ignore[union-attr]
        assert "Use filter to narrow" in text
