"""Tests for the UpdateTools class."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import create_connected_server_and_client_session

from mcp_tools_sql.backends.sqlite import SQLiteBackend
from mcp_tools_sql.config.models import (
    ConnectionConfig,
    QueryConfig,
    UpdateConfig,
    UpdateFieldConfig,
    UpdateKeyConfig,
)
from mcp_tools_sql.identifiers import IDENTIFIER_PATTERN
from mcp_tools_sql.query_tools import QueryTools
from mcp_tools_sql.update_tools import UpdateTools


def _sqlite_backend(db_path: Path) -> SQLiteBackend:
    """Return a connected SQLite backend for the given database path."""
    backend = SQLiteBackend(ConnectionConfig(backend="sqlite", path=str(db_path)))
    backend.connect()
    return backend


# ---------------------------------------------------------------------------
# Empty / name / prefix
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_updates_is_noop(sqlite_db: Path) -> None:
    """UpdateTools with no updates registers zero tools (no error)."""
    backend = _sqlite_backend(sqlite_db)
    mcp = FastMCP("test-empty-updates")
    UpdateTools(backend, {}, "sqlite").register(mcp)

    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        result = await client.list_tools()
        assert result.tools == []


@pytest.mark.asyncio
async def test_update_tool_name_is_prefixed(sqlite_db: Path) -> None:
    """Configured update 'set_name' registers as 'update_set_name'."""
    backend = _sqlite_backend(sqlite_db)
    updates = {
        "set_name": UpdateConfig(
            description="Set customer name",
            table="customers",
            key=UpdateKeyConfig(field="id", type="int"),
            fields=[UpdateFieldConfig(field="name", type="str")],
        )
    }
    mcp = FastMCP("test-prefix")
    UpdateTools(backend, updates, "sqlite").register(mcp)

    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        result = await client.list_tools()
        names = {t.name for t in result.tools}
        assert "update_set_name" in names
        assert "set_name" not in names


def test_invalid_tool_name_raises(sqlite_db: Path) -> None:
    """Invalid tool name raises ValueError mentioning the offending name."""
    backend = _sqlite_backend(sqlite_db)
    updates = {
        "bad-name": UpdateConfig(
            description="Bad",
            table="customers",
            key=UpdateKeyConfig(field="id", type="int"),
            fields=[UpdateFieldConfig(field="name")],
        )
    }
    mcp = FastMCP("test-bad-name")
    with pytest.raises(ValueError, match="bad-name"):
        UpdateTools(backend, updates, "sqlite").register(mcp)


# ---------------------------------------------------------------------------
# Identifier whitelist
# ---------------------------------------------------------------------------


def test_invalid_table_identifier_raises(sqlite_db: Path) -> None:
    backend = _sqlite_backend(sqlite_db)
    updates = {
        "set_name": UpdateConfig(
            description="",
            table="orders; DROP",
            key=UpdateKeyConfig(field="id"),
            fields=[UpdateFieldConfig(field="name")],
        )
    }
    mcp = FastMCP("test-bad-table")
    with pytest.raises(ValueError) as exc:
        UpdateTools(backend, updates, "sqlite").register(mcp)
    msg = str(exc.value)
    assert "intentionally restricted" in msg
    assert IDENTIFIER_PATTERN.pattern in msg


def test_invalid_schema_identifier_raises(sqlite_db: Path) -> None:
    backend = _sqlite_backend(sqlite_db)
    updates = {
        "set_name": UpdateConfig(
            description="",
            schema="dbo prod",
            table="customers",
            key=UpdateKeyConfig(field="id"),
            fields=[UpdateFieldConfig(field="name")],
        )
    }
    mcp = FastMCP("test-bad-schema")
    with pytest.raises(ValueError) as exc:
        UpdateTools(backend, updates, "sqlite").register(mcp)
    msg = str(exc.value)
    assert "intentionally restricted" in msg
    assert IDENTIFIER_PATTERN.pattern in msg


def test_empty_schema_skips_identifier_check(sqlite_db: Path) -> None:
    """Empty ``schema_name`` does not trigger the identifier whitelist."""
    backend = _sqlite_backend(sqlite_db)
    updates = {
        "set_name": UpdateConfig(
            description="",
            schema="",
            table="customers",
            key=UpdateKeyConfig(field="id"),
            fields=[UpdateFieldConfig(field="name")],
        )
    }
    mcp = FastMCP("test-empty-schema")
    UpdateTools(backend, updates, "sqlite").register(mcp)


def test_invalid_key_field_identifier_raises(sqlite_db: Path) -> None:
    backend = _sqlite_backend(sqlite_db)
    updates = {
        "set_name": UpdateConfig(
            description="",
            table="customers",
            key=UpdateKeyConfig(field="id; DROP"),
            fields=[UpdateFieldConfig(field="name")],
        )
    }
    mcp = FastMCP("test-bad-key")
    with pytest.raises(ValueError) as exc:
        UpdateTools(backend, updates, "sqlite").register(mcp)
    msg = str(exc.value)
    assert "intentionally restricted" in msg


def test_invalid_field_identifier_raises(sqlite_db: Path) -> None:
    backend = _sqlite_backend(sqlite_db)
    updates = {
        "set_name": UpdateConfig(
            description="",
            table="customers",
            key=UpdateKeyConfig(field="id"),
            fields=[UpdateFieldConfig(field="bad-col")],
        )
    }
    mcp = FastMCP("test-bad-field")
    with pytest.raises(ValueError) as exc:
        UpdateTools(backend, updates, "sqlite").register(mcp)
    msg = str(exc.value)
    assert "intentionally restricted" in msg


# ---------------------------------------------------------------------------
# key=None
# ---------------------------------------------------------------------------


def test_key_none_raises_at_registration(sqlite_db: Path) -> None:
    backend = _sqlite_backend(sqlite_db)
    updates = {
        "set_name": UpdateConfig(
            description="",
            table="customers",
            key=None,
            fields=[UpdateFieldConfig(field="name")],
        )
    }
    mcp = FastMCP("test-no-key")
    with pytest.raises(ValueError, match="requires a key field"):
        UpdateTools(backend, updates, "sqlite").register(mcp)


# ---------------------------------------------------------------------------
# Signature / JSON schema
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_json_schema_key_required_fields_optional(sqlite_db: Path) -> None:
    backend = _sqlite_backend(sqlite_db)
    updates = {
        "set_name": UpdateConfig(
            description="Set name",
            table="customers",
            key=UpdateKeyConfig(field="id", type="int", description="Customer ID"),
            fields=[
                UpdateFieldConfig(field="name", type="str", description="New name"),
                UpdateFieldConfig(
                    field="country", type="str", description="New country"
                ),
            ],
        )
    }
    mcp = FastMCP("test-schema")
    UpdateTools(backend, updates, "sqlite").register(mcp)

    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        result = await client.list_tools()
        tool = next(t for t in result.tools if t.name == "update_set_name")
        schema = tool.inputSchema
        props = schema["properties"]
        assert "id" in props
        assert "name" in props
        assert "country" in props
        required = schema.get("required", [])
        assert "id" in required
        assert "name" not in required
        assert "country" not in required


@pytest.mark.asyncio
async def test_json_schema_required_field_in_required_list(sqlite_db: Path) -> None:
    backend = _sqlite_backend(sqlite_db)
    updates = {
        "set_status": UpdateConfig(
            description="Set status",
            table="orders",
            key=UpdateKeyConfig(field="id", type="int"),
            fields=[
                UpdateFieldConfig(field="status", type="str", required=True),
            ],
        )
    }
    mcp = FastMCP("test-required-schema")
    UpdateTools(backend, updates, "sqlite").register(mcp)

    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        result = await client.list_tools()
        tool = next(t for t in result.tools if t.name == "update_set_status")
        required = tool.inputSchema.get("required", [])
        assert "status" in required


# ---------------------------------------------------------------------------
# Round-trip with SQLite
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_and_call_updates_row(sqlite_db: Path) -> None:
    backend = _sqlite_backend(sqlite_db)
    updates = {
        "set_name": UpdateConfig(
            description="Set customer name",
            table="customers",
            key=UpdateKeyConfig(field="id", type="int"),
            fields=[UpdateFieldConfig(field="name", type="str")],
        )
    }
    mcp = FastMCP("test-roundtrip")
    UpdateTools(backend, updates, "sqlite").register(mcp)

    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        result = await client.call_tool("update_set_name", {"id": 1, "name": "Updated"})
        text = result.content[0].text  # type: ignore[union-attr]
        assert "1 row" in text

    rows = backend.execute_query("SELECT name FROM customers WHERE id = :id", {"id": 1})
    assert rows[0]["name"] == "Updated"


# ---------------------------------------------------------------------------
# Partial / sentinel semantics
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_partial_update_only_provided_fields_in_sql(
    sqlite_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = _sqlite_backend(sqlite_db)
    captured: dict[str, Any] = {}
    original = backend.execute_update

    def spy(sql: str, params: dict[str, Any] | None = None) -> int:
        captured["sql"] = sql
        captured["params"] = params
        return original(sql, params)

    monkeypatch.setattr(backend, "execute_update", spy)

    updates = {
        "set_profile": UpdateConfig(
            description="",
            table="customers",
            key=UpdateKeyConfig(field="id", type="int"),
            fields=[
                UpdateFieldConfig(field="name", type="str"),
                UpdateFieldConfig(field="country", type="str"),
            ],
        )
    }
    mcp = FastMCP("test-partial")
    UpdateTools(backend, updates, "sqlite").register(mcp)

    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        await client.call_tool("update_set_profile", {"id": 1, "name": "OnlyName"})

    assert "SET name=:name" in captured["sql"]
    assert "country" not in captured["sql"]


@pytest.mark.asyncio
async def test_explicit_none_emits_null(
    sqlite_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = _sqlite_backend(sqlite_db)
    captured: dict[str, Any] = {}
    original = backend.execute_update

    def spy(sql: str, params: dict[str, Any] | None = None) -> int:
        captured["sql"] = sql
        captured["params"] = params
        return original(sql, params)

    monkeypatch.setattr(backend, "execute_update", spy)

    updates = {
        "set_country": UpdateConfig(
            description="",
            table="customers",
            key=UpdateKeyConfig(field="id", type="int"),
            fields=[UpdateFieldConfig(field="country", type="str")],
        )
    }
    mcp = FastMCP("test-explicit-none")
    UpdateTools(backend, updates, "sqlite").register(mcp)

    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        await client.call_tool("update_set_country", {"id": 1, "country": None})

    assert "country=:country" in captured["sql"]
    assert captured["params"] is not None
    assert "country" in captured["params"]
    assert captured["params"]["country"] is None


# ---------------------------------------------------------------------------
# Zero-field rejection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_zero_fields_passed_rejected_no_db_call(
    sqlite_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = _sqlite_backend(sqlite_db)
    calls: list[Any] = []
    original = backend.execute_update

    def spy(sql: str, params: dict[str, Any] | None = None) -> int:
        calls.append((sql, params))
        return original(sql, params)

    monkeypatch.setattr(backend, "execute_update", spy)

    updates = {
        "set_anything": UpdateConfig(
            description="",
            table="customers",
            key=UpdateKeyConfig(field="id", type="int"),
            fields=[
                UpdateFieldConfig(field="name", type="str"),
                UpdateFieldConfig(field="country", type="str"),
            ],
        )
    }
    mcp = FastMCP("test-zero-fields")
    UpdateTools(backend, updates, "sqlite").register(mcp)

    async with create_connected_server_and_client_session(mcp) as client:
        result = await client.call_tool("update_set_anything", {"id": 1})
        assert result.isError

    assert calls == []


# ---------------------------------------------------------------------------
# Key not found
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_key_not_found_returns_no_row_text(sqlite_db: Path) -> None:
    backend = _sqlite_backend(sqlite_db)
    updates = {
        "set_name": UpdateConfig(
            description="",
            table="customers",
            key=UpdateKeyConfig(field="id", type="int"),
            fields=[UpdateFieldConfig(field="name", type="str")],
        )
    }
    mcp = FastMCP("test-missing-key")
    UpdateTools(backend, updates, "sqlite").register(mcp)

    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        result = await client.call_tool(
            "update_set_name", {"id": 999, "name": "Nobody"}
        )
        assert not result.isError
        text = result.content[0].text  # type: ignore[union-attr]
        assert "No row found" in text


# ---------------------------------------------------------------------------
# >1 affected rows (warning)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_multiple_rows_returns_warning_token(tmp_path: Path) -> None:
    db_path = tmp_path / "multi.db"
    import sqlite3

    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE multi_key_test (k TEXT, v TEXT)")
    conn.execute("INSERT INTO multi_key_test VALUES ('dup', 'a')")
    conn.execute("INSERT INTO multi_key_test VALUES ('dup', 'b')")
    conn.commit()
    conn.close()

    backend = _sqlite_backend(db_path)
    updates = {
        "set_v": UpdateConfig(
            description="",
            table="multi_key_test",
            key=UpdateKeyConfig(field="k", type="str"),
            fields=[UpdateFieldConfig(field="v", type="str")],
        )
    }
    mcp = FastMCP("test-multi")
    UpdateTools(backend, updates, "sqlite").register(mcp)

    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        result = await client.call_tool("update_set_v", {"k": "dup", "v": "new"})
        text = result.content[0].text  # type: ignore[union-attr]
        assert "WARNING:" in text
        assert "2" in text


# ---------------------------------------------------------------------------
# SQL injection prevention
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sql_injection_blocked_via_values(sqlite_db: Path) -> None:
    backend = _sqlite_backend(sqlite_db)
    updates = {
        "set_name": UpdateConfig(
            description="",
            table="customers",
            key=UpdateKeyConfig(field="id", type="int"),
            fields=[UpdateFieldConfig(field="name", type="str")],
        )
    }
    mcp = FastMCP("test-inject-value")
    UpdateTools(backend, updates, "sqlite").register(mcp)

    payload = "'); DROP TABLE customers; --"
    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        await client.call_tool("update_set_name", {"id": 1, "name": payload})

    rows = backend.execute_query("SELECT name FROM customers WHERE id = :id", {"id": 1})
    assert rows[0]["name"] == payload
    count_rows = backend.execute_query("SELECT count(*) AS c FROM customers")
    assert count_rows[0]["c"] >= 1


@pytest.mark.asyncio
async def test_sql_injection_blocked_via_key_value(sqlite_db: Path) -> None:
    backend = _sqlite_backend(sqlite_db)
    updates = {
        "set_name": UpdateConfig(
            description="",
            table="customers",
            key=UpdateKeyConfig(field="name", type="str"),
            fields=[UpdateFieldConfig(field="country", type="str")],
        )
    }
    mcp = FastMCP("test-inject-key")
    UpdateTools(backend, updates, "sqlite").register(mcp)

    payload = "'); DROP TABLE customers; --"
    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        await client.call_tool("update_set_name", {"name": payload, "country": "X"})

    count_rows = backend.execute_query("SELECT count(*) AS c FROM customers")
    assert count_rows[0]["c"] >= 1


# ---------------------------------------------------------------------------
# Required field omitted
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_required_field_omitted_errors(sqlite_db: Path) -> None:
    backend = _sqlite_backend(sqlite_db)
    updates = {
        "set_status": UpdateConfig(
            description="",
            table="orders",
            key=UpdateKeyConfig(field="id", type="int"),
            fields=[
                UpdateFieldConfig(field="status", type="str", required=True),
            ],
        )
    }
    mcp = FastMCP("test-required")
    UpdateTools(backend, updates, "sqlite").register(mcp)

    async with create_connected_server_and_client_session(mcp) as client:
        result = await client.call_tool("update_set_status", {"id": 1})
        assert result.isError


# ---------------------------------------------------------------------------
# Schema empty vs nonempty in generated SQL
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_schema_empty_generates_bare_table(
    sqlite_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = _sqlite_backend(sqlite_db)
    captured: dict[str, Any] = {}
    original = backend.execute_update

    def spy(sql: str, params: dict[str, Any] | None = None) -> int:
        captured["sql"] = sql
        return original(sql, params)

    monkeypatch.setattr(backend, "execute_update", spy)

    updates = {
        "set_name": UpdateConfig(
            description="",
            schema="",
            table="customers",
            key=UpdateKeyConfig(field="id", type="int"),
            fields=[UpdateFieldConfig(field="name", type="str")],
        )
    }
    mcp = FastMCP("test-bare")
    UpdateTools(backend, updates, "sqlite").register(mcp)

    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        await client.call_tool("update_set_name", {"id": 1, "name": "X"})

    assert captured["sql"].startswith("UPDATE customers ")


@pytest.mark.asyncio
async def test_schema_nonempty_generates_qualified_table(
    sqlite_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = _sqlite_backend(sqlite_db)
    captured: dict[str, Any] = {}
    original = backend.execute_update

    def spy(sql: str, params: dict[str, Any] | None = None) -> int:
        captured["sql"] = sql
        return original(sql, params)

    monkeypatch.setattr(backend, "execute_update", spy)

    updates = {
        "set_name": UpdateConfig(
            description="",
            schema="main",
            table="customers",
            key=UpdateKeyConfig(field="id", type="int"),
            fields=[UpdateFieldConfig(field="name", type="str")],
        )
    }
    mcp = FastMCP("test-qualified")
    UpdateTools(backend, updates, "sqlite").register(mcp)

    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        await client.call_tool("update_set_name", {"id": 1, "name": "Y"})

    assert "UPDATE main.customers " in captured["sql"]


# ---------------------------------------------------------------------------
# Name collision
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_query_and_update_same_base_name_coexist(sqlite_db: Path) -> None:
    backend = _sqlite_backend(sqlite_db)
    queries = {
        "foo": QueryConfig(
            description="",
            sql="SELECT 1 AS a",
        )
    }
    updates = {
        "foo": UpdateConfig(
            description="",
            table="customers",
            key=UpdateKeyConfig(field="id", type="int"),
            fields=[UpdateFieldConfig(field="name", type="str")],
        )
    }
    mcp = FastMCP("test-coexist")
    QueryTools(backend, queries, "sqlite").register(mcp)
    UpdateTools(backend, updates, "sqlite").register(mcp)

    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        result = await client.list_tools()
        names = {t.name for t in result.tools}
        assert "query_foo" in names
        assert "update_foo" in names


# ---------------------------------------------------------------------------
# Field/key collision
# ---------------------------------------------------------------------------


def test_field_name_clashes_with_key_raises_at_registration(sqlite_db: Path) -> None:
    backend = _sqlite_backend(sqlite_db)
    updates = {
        "set_id": UpdateConfig(
            description="",
            table="customers",
            key=UpdateKeyConfig(field="id", type="int"),
            fields=[UpdateFieldConfig(field="id", type="int")],
        )
    }
    mcp = FastMCP("test-clash")
    with pytest.raises(ValueError) as exc:
        UpdateTools(backend, updates, "sqlite").register(mcp)
    msg = str(exc.value)
    assert "id" in msg


# ---------------------------------------------------------------------------
# Shared identifier error message
# ---------------------------------------------------------------------------


def test_identifier_error_message_shared(sqlite_db: Path) -> None:
    """The canonical error message produced by update_tools matches the helper."""
    from mcp_tools_sql.identifiers import identifier_error

    backend = _sqlite_backend(sqlite_db)
    updates = {
        "set_name": UpdateConfig(
            description="",
            table="bad-table",
            key=UpdateKeyConfig(field="id", type="int"),
            fields=[UpdateFieldConfig(field="name")],
        )
    }
    mcp = FastMCP("test-shared-msg")
    with pytest.raises(ValueError) as exc:
        UpdateTools(backend, updates, "sqlite").register(mcp)
    assert str(exc.value) == identifier_error("bad-table", "set_name")
