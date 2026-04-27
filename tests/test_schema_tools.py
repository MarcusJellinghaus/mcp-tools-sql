"""Tests for schema_tools helper functions and integration tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import create_connected_server_and_client_session

from mcp_tools_sql.backends.sqlite import SQLiteBackend
from mcp_tools_sql.config.models import ConnectionConfig
from mcp_tools_sql.schema_tools import (
    _apply_filter,
    _extract_sql_params,
    register_builtin_tools,
)


class TestExtractSqlParams:
    """Tests for _extract_sql_params."""

    def test_single_param(self) -> None:
        assert _extract_sql_params("SELECT * WHERE x = :id") == {"id"}

    def test_multiple_params(self) -> None:
        assert _extract_sql_params("WHERE a = :x AND b = :y") == {"x", "y"}

    def test_no_params(self) -> None:
        assert _extract_sql_params("SELECT 'main' AS name") == set()

    def test_duplicate_param(self) -> None:
        assert _extract_sql_params("WHERE a = :x OR b = :x") == {"x"}


class TestApplyFilter:
    """Tests for _apply_filter."""

    def test_no_filter(self) -> None:
        """None filter returns all rows."""
        rows = [{"name": "a"}, {"name": "b"}]
        assert _apply_filter(rows, None) == rows

    def test_glob_match(self) -> None:
        """Glob pattern filters rows by 'name' field."""
        rows = [
            {"name": "user_id"},
            {"name": "user_name"},
            {"name": "order_id"},
        ]
        result = _apply_filter(rows, "user_*")
        assert result == [{"name": "user_id"}, {"name": "user_name"}]

    def test_case_insensitive(self) -> None:
        """Filter is case-insensitive."""
        rows = [{"name": "User_ID"}, {"name": "order_id"}]
        result = _apply_filter(rows, "user_*")
        assert result == [{"name": "User_ID"}]

    def test_no_match(self) -> None:
        """No matching rows returns empty list."""
        rows = [{"name": "a"}, {"name": "b"}]
        assert _apply_filter(rows, "z*") == []


# ---------------------------------------------------------------------------
# Helper: create FastMCP with registered builtin tools against a SQLite DB
# ---------------------------------------------------------------------------


def _make_mcp_with_tools(db_path: str) -> FastMCP:
    """Create a FastMCP instance with builtin tools registered against a SQLite DB."""
    config = ConnectionConfig(backend="sqlite", connection_string=db_path)
    backend = SQLiteBackend(config)
    backend.connect()
    mcp = FastMCP("test-schema-tools")
    register_builtin_tools(mcp, backend, "sqlite")
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
        """call_tool('read_columns', {filter: 'na*'}) filters by glob."""
        mcp = _make_mcp_with_tools(str(sqlite_db))
        async with create_connected_server_and_client_session(
            mcp, raise_exceptions=True
        ) as client:
            result = await client.call_tool(
                "read_columns",
                {"schema": "main", "table": "customers", "filter": "na*"},
            )
            text = result.content[0].text  # type: ignore[union-attr]
            assert "name" in text
            assert "country" not in text.split("name")[-1] or "country" not in text

    async def test_read_columns_filter_no_match(self, sqlite_db: Path) -> None:
        """Filter with no matches returns 'No results found.'."""
        mcp = _make_mcp_with_tools(str(sqlite_db))
        async with create_connected_server_and_client_session(
            mcp, raise_exceptions=True
        ) as client:
            result = await client.call_tool(
                "read_columns",
                {"schema": "main", "table": "customers", "filter": "zzz*"},
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
