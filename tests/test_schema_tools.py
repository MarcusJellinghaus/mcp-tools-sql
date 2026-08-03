"""Tests for schema_tools helper functions and integration tests."""

from __future__ import annotations

import inspect
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any, get_args

import pytest
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import create_connected_server_and_client_session

from mcp_tools_sql.backends.base import DatabaseBackend
from mcp_tools_sql.backends.sqlite import SQLiteBackend
from mcp_tools_sql.config.models import (
    BackendQueryConfig,
    ConnectionConfig,
    QueryConfig,
    ResolvedTarget,
    ResolvedTargets,
)
from mcp_tools_sql.query_helpers import (
    build_query_body,
    build_query_sig_params,
    build_schema_body,
    build_target_params,
)
from mcp_tools_sql.schema_tools import (
    SchemaTools,
    build_read_databases_tool,
    load_default_queries,
)
from mcp_tools_sql.tool_builder import build_tool_fn
from tests.target_helpers import RecordingRegistry, make_target, single_target


def _assemble(
    name: str,
    config: QueryConfig,
    backend: SQLiteBackend,
    backend_name: str = "sqlite",
    truncation_hint: str = "",
) -> Callable[..., Any]:
    """Helper: build sig_params + body then call the assembler."""
    sig_params = build_query_sig_params(config)
    body = build_query_body(name, config, backend, backend_name, truncation_hint)
    return build_tool_fn(name, sig_params, body, config.description)


# ---------------------------------------------------------------------------
# Helper: create FastMCP with registered builtin tools against a SQLite DB
# ---------------------------------------------------------------------------


def _make_mcp_with_tools(db_path: str) -> FastMCP:
    """Create a FastMCP instance with builtin tools registered against a SQLite DB."""
    config = ConnectionConfig(backend="sqlite", path=db_path)
    backend = SQLiteBackend(config)
    backend.connect()
    mcp = FastMCP("test-schema-tools")
    SchemaTools(*single_target(backend)).register(mcp)
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
    fn = _assemble("read_tables", queries["read_tables"], backend, "sqlite")

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
    fn = _assemble("clamp_test", qcfg, backend, "sqlite")

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
    fn = _assemble(
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


# ---------------------------------------------------------------------------
# build_read_databases_tool (config-only, no backend access)
# ---------------------------------------------------------------------------


def _target(
    connection: str,
    database: str,
    *,
    backend_name: str = "sqlite",
    is_default: bool = False,
    connection_description: str = "",
    database_description: str = "",
) -> ResolvedTarget:
    """Build a ResolvedTarget with an arbitrary (unused-at-runtime) config."""
    return ResolvedTarget(
        connection=connection,
        database=database,
        config=ConnectionConfig(backend="sqlite", path="unused.db"),
        backend_name=backend_name,
        is_default=is_default,
        connection_description=connection_description,
        database_description=database_description,
    )


@pytest.mark.asyncio
async def test_read_databases_lists_every_target_in_config_order() -> None:
    """The tool tabulates each configured target in config order."""
    t1 = _target("prod", "sales", is_default=True, database_description="Sales DB")
    t2 = _target("prod", "hr", database_description="HR DB")
    t3 = _target("analytics", "warehouse", backend_name="postgresql")
    targets = ResolvedTargets(
        targets=[t1, t2, t3], default=t1, file_default_connection="prod"
    )

    text = await build_read_databases_tool(targets)()

    # All targets present, in config order (sales before hr before warehouse).
    assert text.index("sales") < text.index("hr") < text.index("warehouse")
    assert "analytics" in text
    assert "postgresql" in text


@pytest.mark.asyncio
async def test_read_databases_marks_only_the_default() -> None:
    """``is_default`` is True for exactly the default target."""
    t1 = _target("prod", "sales", is_default=True)
    t2 = _target("prod", "hr")
    targets = ResolvedTargets(
        targets=[t1, t2], default=t1, file_default_connection="prod"
    )

    text = await build_read_databases_tool(targets)()

    assert "True" in text
    assert "False" in text


@pytest.mark.asyncio
async def test_read_databases_description_falls_back_to_connection() -> None:
    """Row description prefers db description, else the connection description."""
    t1 = _target(
        "prod",
        "sales",
        is_default=True,
        connection_description="Prod server",
        database_description="Sales catalog",
    )
    t2 = _target("prod", "hr", connection_description="Prod server")
    targets = ResolvedTargets(
        targets=[t1, t2], default=t1, file_default_connection="prod"
    )

    text = await build_read_databases_tool(targets)()

    assert "Sales catalog" in text  # db description wins when present
    assert "Prod server" in text  # falls back to connection description


@pytest.mark.asyncio
async def test_read_databases_performs_no_backend_access() -> None:
    """The tool takes only targets — calling it never touches a backend."""
    t1 = _target("prod", "sales", is_default=True)
    t2 = _target("prod", "hr")
    targets = ResolvedTargets(
        targets=[t1, t2], default=t1, file_default_connection="prod"
    )

    # No registry / backend is involved at all; the call simply succeeds.
    text = await build_read_databases_tool(targets)()

    assert "sales" in text
    assert "hr" in text


# ---------------------------------------------------------------------------
# build_target_params — conditional keyword-only selector params (Step 10)
# ---------------------------------------------------------------------------


def _single_sqlite_targets() -> ResolvedTargets:
    """One-target install (single connection, single database)."""
    t = make_target("default", "main", is_default=True, default_database="main")
    return ResolvedTargets(targets=[t], default=t, file_default_connection="default")


def _multi_targets() -> ResolvedTargets:
    """Two connections; the default connection has two databases.

    ``default`` → ``sales`` (default) + ``hr``; ``other`` → ``warehouse``.
    ``mssql`` backends keep the authored ``default_database`` (SQLite would
    normalise every catalog to ``main``), so ``resolve_pinned`` can fall back to
    the connection default. The plain SQL still runs on the real SQLite backend.
    """
    t_default = make_target(
        "default",
        "sales",
        is_default=True,
        default_database="sales",
        backend_name="mssql",
    )
    t_hr = make_target("default", "hr", default_database="sales", backend_name="mssql")
    t_other = make_target(
        "other", "warehouse", default_database="warehouse", backend_name="mssql"
    )
    return ResolvedTargets(
        targets=[t_default, t_hr, t_other],
        default=t_default,
        file_default_connection="default",
    )


def _literal_members(annotation: Any) -> set[str]:
    """Extract the ``Literal`` members from an ``Annotated[...]`` param annotation."""
    inner = get_args(annotation)[0]  # unwrap Annotated -> Literal | Optional[Literal]
    literal = inner
    nested = get_args(inner)
    # Optional[Literal[...]] -> (Literal[...], NoneType)
    if nested and get_args(nested[0]):
        literal = nested[0]
    return set(get_args(literal))


def test_build_target_params_empty_for_single_target() -> None:
    """A single-target install adds no selector params (byte-identical sig)."""
    assert build_target_params(_single_sqlite_targets()) == []


def test_build_target_params_two_connections_yields_both() -> None:
    """More than one connection yields both keyword-only connection+database."""
    params = build_target_params(_multi_targets())

    assert [p.name for p in params] == ["connection", "database"]
    assert all(p.kind == inspect.Parameter.KEYWORD_ONLY for p in params)


def test_build_target_params_one_connection_two_databases_yields_database_only() -> (
    None
):
    """A single connection with two databases yields only the database param."""
    t_sales = make_target("default", "sales", is_default=True, default_database="sales")
    t_hr = make_target("default", "hr", default_database="sales")
    targets = ResolvedTargets(
        targets=[t_sales, t_hr], default=t_sales, file_default_connection="default"
    )

    params = build_target_params(targets)

    assert [p.name for p in params] == ["database"]
    assert params[0].kind == inspect.Parameter.KEYWORD_ONLY


def test_build_target_params_enum_members_and_defaults() -> None:
    """Enums list the right names; connection defaults to the file default, database to None."""
    params = {p.name: p for p in build_target_params(_multi_targets())}

    conn = params["connection"]
    assert conn.default == "default"
    assert _literal_members(conn.annotation) == {"default", "other"}

    db = params["database"]
    assert db.default is None
    assert _literal_members(db.annotation) == {"sales", "hr", "warehouse"}


# ---------------------------------------------------------------------------
# build_schema_body — runtime single-target resolution (Step 10)
# ---------------------------------------------------------------------------


def _tables_config() -> QueryConfig:
    """A backend-agnostic read_tables-style query that runs on SQLite."""
    return QueryConfig(
        description="List tables",
        sql="SELECT name FROM sqlite_master WHERE type = 'table'",
    )


@pytest.mark.asyncio
async def test_schema_body_binds_selected_database(sqlite_db: Path) -> None:
    """`database='hr'` resolves against the (default_conn, hr) backend."""
    backend = SQLiteBackend(ConnectionConfig(backend="sqlite", path=str(sqlite_db)))
    backend.connect()
    targets = _multi_targets()
    registry = RecordingRegistry(
        {
            ("default", "sales"): backend,
            ("default", "hr"): backend,
            ("other", "warehouse"): backend,
        }
    )

    body = build_schema_body("read_tables", _tables_config(), registry, targets, "")
    text = await body(database="hr")

    assert registry.calls[-1].connection == "default"
    assert registry.calls[-1].database == "hr"
    assert "customers" in text  # the query actually executed


@pytest.mark.asyncio
async def test_schema_body_connection_only_uses_connection_default(
    sqlite_db: Path,
) -> None:
    """`connection='other'` with no database resolves that connection's default."""
    backend = SQLiteBackend(ConnectionConfig(backend="sqlite", path=str(sqlite_db)))
    backend.connect()
    targets = _multi_targets()
    registry = RecordingRegistry(
        {
            ("default", "sales"): backend,
            ("default", "hr"): backend,
            ("other", "warehouse"): backend,
        }
    )

    body = build_schema_body("read_tables", _tables_config(), registry, targets, "")
    await body(connection="other")

    assert registry.calls[-1].connection == "other"
    assert registry.calls[-1].database == "warehouse"


@pytest.mark.asyncio
async def test_schema_body_cross_connection_mismatch_returns_verdict(
    sqlite_db: Path,
) -> None:
    """An (other, hr) mismatch returns a friendly verdict and hits no backend."""
    backend = SQLiteBackend(ConnectionConfig(backend="sqlite", path=str(sqlite_db)))
    backend.connect()
    targets = _multi_targets()
    registry = RecordingRegistry(
        {
            ("default", "sales"): backend,
            ("default", "hr"): backend,
            ("other", "warehouse"): backend,
        }
    )

    body = build_schema_body("read_tables", _tables_config(), registry, targets, "")
    text = await body(connection="other", database="hr")

    assert "other" in text
    assert "hr" in text
    assert "warehouse" in text  # lists the available databases
    assert registry.calls == []  # never resolved a backend


@pytest.mark.asyncio
async def test_schema_body_unpinned_resolves_default_target(sqlite_db: Path) -> None:
    """With no kwargs the body resolves the file default target."""
    backend = SQLiteBackend(ConnectionConfig(backend="sqlite", path=str(sqlite_db)))
    backend.connect()
    targets = _multi_targets()
    registry = RecordingRegistry(
        {
            ("default", "sales"): backend,
            ("default", "hr"): backend,
            ("other", "warehouse"): backend,
        }
    )

    body = build_schema_body("read_tables", _tables_config(), registry, targets, "")
    await body()

    assert registry.calls[-1].connection == "default"
    assert registry.calls[-1].database == "sales"


@pytest.mark.asyncio
async def test_multi_install_exposes_selector_params_in_schema(
    sqlite_db: Path,
) -> None:
    """A multi-target install exposes connection/database enums on read_tables."""
    backend = SQLiteBackend(ConnectionConfig(backend="sqlite", path=str(sqlite_db)))
    backend.connect()
    targets = _multi_targets()
    registry = RecordingRegistry(
        {
            ("default", "sales"): backend,
            ("default", "hr"): backend,
            ("other", "warehouse"): backend,
        }
    )
    mcp = FastMCP("test-multi-schema")
    SchemaTools(registry, targets).register(mcp)

    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        result = await client.list_tools()
        tool = next(t for t in result.tools if t.name == "read_tables")
        props = tool.inputSchema["properties"]
        assert "connection" in props
        assert "database" in props
        # Enum members are surfaced to the caller (invalid values rejected).
        import json

        db_schema = json.dumps(props["database"])
        assert "sales" in db_schema
        assert "hr" in db_schema
        assert "warehouse" in db_schema


# ---------------------------------------------------------------------------
# build_schema_body — database="*" fan-out (Step 11)
# ---------------------------------------------------------------------------


class _FanoutBackend(DatabaseBackend):
    """A minimal backend that returns preset rows (or raises) on query."""

    def __init__(
        self,
        rows: list[dict[str, Any]],
        *,
        raises: Exception | None = None,
    ) -> None:
        self._rows = rows
        self._raises = raises

    def connect(self) -> None:
        """No-op connect."""

    def close(self) -> None:
        """No-op close."""

    def execute_query(
        self, sql: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Return fresh copies of the preset rows, or raise if configured.

        Returns:
            Shallow copies of the seeded rows so downstream ``_database``
            tagging never mutates the fixture.
        """
        if self._raises is not None:
            raise self._raises
        return [dict(r) for r in self._rows]

    def execute_readonly_query(
        self, sql: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Unused in these tests.

        Raises:
            NotImplementedError: Always.
        """
        raise NotImplementedError

    def execute_update(self, sql: str, params: dict[str, Any] | None = None) -> int:
        """Unused in these tests.

        Raises:
            NotImplementedError: Always.
        """
        raise NotImplementedError

    def explain(self, sql: str, params: dict[str, Any] | None = None) -> str:
        """Unused in these tests.

        Raises:
            NotImplementedError: Always.
        """
        raise NotImplementedError

    def get_isolated_connection(self) -> Any:
        """Unused in these tests.

        Raises:
            NotImplementedError: Always.
        """
        raise NotImplementedError


def _fanout_registry(
    sales: _FanoutBackend,
    hr: _FanoutBackend,
    warehouse: _FanoutBackend | None = None,
) -> RecordingRegistry:
    """Seed a registry for the ``_multi_targets`` connections."""
    return RecordingRegistry(
        {
            ("default", "sales"): sales,
            ("default", "hr"): hr,
            ("other", "warehouse"): warehouse or _FanoutBackend([]),
        }
    )


def _filter_config() -> QueryConfig:
    """A read_columns-style query whose ``name`` column drives the glob filter."""
    return QueryConfig(
        description="List columns",
        sql="SELECT name FROM columns",
        filter_column="name",
    )


@pytest.mark.asyncio
async def test_fanout_merges_rows_with_database_column_in_config_order() -> None:
    """`database='*'` merges every db's rows tagged with `_database`, in order."""
    registry = _fanout_registry(
        _FanoutBackend([{"name": "alice"}, {"name": "amy"}]),
        _FanoutBackend([{"name": "carol"}]),
    )
    body = build_schema_body(
        "read_tables", _tables_config(), registry, _multi_targets(), ""
    )

    text = await body(database="*")

    assert "_database" in text
    assert text.index("alice") < text.index("carol")  # config order: sales, hr
    assert "sales" in text
    assert "hr" in text
    # Fan-out hit both databases of the default connection, in config order.
    assert [(c.connection, c.database) for c in registry.calls] == [
        ("default", "sales"),
        ("default", "hr"),
    ]


@pytest.mark.asyncio
async def test_fanout_footer_counts_exact_and_capped_on_truncation() -> None:
    """Merged total caps at max_rows; footer shows exact per-db counts."""
    registry = _fanout_registry(
        _FanoutBackend([{"id": i} for i in range(3)]),
        _FanoutBackend([{"id": i} for i in range(4)]),
    )
    body = build_schema_body(
        "read_tables", _tables_config(), registry, _multi_targets(), ""
    )

    text = await body(database="*", max_rows=5)

    assert "Showing 5 of 7 rows." in text
    assert "Matched: sales 3, hr 4." in text


@pytest.mark.asyncio
async def test_fanout_footer_absent_without_truncation() -> None:
    """When the merged total fits, no truncation footer is rendered."""
    registry = _fanout_registry(
        _FanoutBackend([{"id": 1}]),
        _FanoutBackend([{"id": 2}]),
    )
    body = build_schema_body(
        "read_tables", _tables_config(), registry, _multi_targets(), ""
    )

    text = await body(database="*", max_rows=100)

    assert "Showing" not in text
    assert "Matched:" not in text


@pytest.mark.asyncio
async def test_fanout_one_target_error_rendered_inline() -> None:
    """A failing database is reported inline; the other's rows still show."""
    registry = _fanout_registry(
        _FanoutBackend([{"name": "alice"}]),
        _FanoutBackend([], raises=RuntimeError("boom")),
    )
    body = build_schema_body(
        "read_tables", _tables_config(), registry, _multi_targets(), ""
    )

    text = await body(database="*")

    assert "alice" in text  # surviving target's rows
    assert "hr:" in text  # errored database named
    assert "boom" in text  # its error surfaced


@pytest.mark.asyncio
async def test_fanout_name_filter_applies_per_target_before_merge() -> None:
    """`name_filter` filters each target before the merge/cap, not after."""
    registry = _fanout_registry(
        _FanoutBackend([{"name": "alpha"}, {"name": "beta"}]),
        _FanoutBackend([{"name": "alfred"}, {"name": "gamma"}]),
    )
    body = build_schema_body(
        "read_columns", _filter_config(), registry, _multi_targets(), ""
    )

    text = await body(database="*", name_filter="al*")

    assert "alpha" in text  # matched in sales
    assert "alfred" in text  # matched in hr
    assert "beta" not in text
    assert "gamma" not in text


@pytest.mark.asyncio
async def test_pinned_database_has_no_database_column() -> None:
    """The single-target path never adds a `_database` column (Step 10 intact)."""
    registry = _fanout_registry(
        _FanoutBackend([{"name": "alice"}]),
        _FanoutBackend([{"name": "carol"}]),
    )
    body = build_schema_body(
        "read_tables", _tables_config(), registry, _multi_targets(), ""
    )

    text = await body(database="hr")

    assert "carol" in text
    assert "_database" not in text
