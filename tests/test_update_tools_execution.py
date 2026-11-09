"""Tests for calling registered UpdateTools against SQLite."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import create_connected_server_and_client_session

from mcp_tools_sql.config.models import (
    UpdateConfig,
    UpdateFieldConfig,
    UpdateKeyConfig,
)
from mcp_tools_sql.server import FastMCPSink
from mcp_tools_sql.update_tools import UpdateTools
from tests.target_helpers import single_target, sqlite_backend

# ---------------------------------------------------------------------------
# Round-trip with SQLite
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_and_call_updates_row(sqlite_db: Path) -> None:
    backend = sqlite_backend(sqlite_db)
    updates = {
        "set_name": UpdateConfig(
            description="Set customer name",
            table="customers",
            key=UpdateKeyConfig(field="id", type="int"),
            fields=[UpdateFieldConfig(field="name", type="str")],
        )
    }
    mcp = FastMCP("test-roundtrip")
    UpdateTools(*single_target(backend), updates).register(FastMCPSink(mcp))

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
    backend = sqlite_backend(sqlite_db)
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
    UpdateTools(*single_target(backend), updates).register(FastMCPSink(mcp))

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
    backend = sqlite_backend(sqlite_db)
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
    UpdateTools(*single_target(backend), updates).register(FastMCPSink(mcp))

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
    backend = sqlite_backend(sqlite_db)
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
    UpdateTools(*single_target(backend), updates).register(FastMCPSink(mcp))

    async with create_connected_server_and_client_session(mcp) as client:
        result = await client.call_tool("update_set_anything", {"id": 1})
        assert result.isError

    assert calls == []


# ---------------------------------------------------------------------------
# Key not found
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_key_not_found_returns_no_row_text(sqlite_db: Path) -> None:
    backend = sqlite_backend(sqlite_db)
    updates = {
        "set_name": UpdateConfig(
            description="",
            table="customers",
            key=UpdateKeyConfig(field="id", type="int"),
            fields=[UpdateFieldConfig(field="name", type="str")],
        )
    }
    mcp = FastMCP("test-missing-key")
    UpdateTools(*single_target(backend), updates).register(FastMCPSink(mcp))

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

    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE multi_key_test (k TEXT, v TEXT)")
    conn.execute("INSERT INTO multi_key_test VALUES ('dup', 'a')")
    conn.execute("INSERT INTO multi_key_test VALUES ('dup', 'b')")
    conn.commit()
    conn.close()

    backend = sqlite_backend(db_path)
    updates = {
        "set_v": UpdateConfig(
            description="",
            table="multi_key_test",
            key=UpdateKeyConfig(field="k", type="str"),
            fields=[UpdateFieldConfig(field="v", type="str")],
        )
    }
    mcp = FastMCP("test-multi")
    UpdateTools(*single_target(backend), updates).register(FastMCPSink(mcp))

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
    backend = sqlite_backend(sqlite_db)
    updates = {
        "set_name": UpdateConfig(
            description="",
            table="customers",
            key=UpdateKeyConfig(field="id", type="int"),
            fields=[UpdateFieldConfig(field="name", type="str")],
        )
    }
    mcp = FastMCP("test-inject-value")
    UpdateTools(*single_target(backend), updates).register(FastMCPSink(mcp))

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
    backend = sqlite_backend(sqlite_db)
    updates = {
        "set_name": UpdateConfig(
            description="",
            table="customers",
            key=UpdateKeyConfig(field="name", type="str"),
            fields=[UpdateFieldConfig(field="country", type="str")],
        )
    }
    mcp = FastMCP("test-inject-key")
    UpdateTools(*single_target(backend), updates).register(FastMCPSink(mcp))

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
    backend = sqlite_backend(sqlite_db)
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
    UpdateTools(*single_target(backend), updates).register(FastMCPSink(mcp))

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
    backend = sqlite_backend(sqlite_db)
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
    UpdateTools(*single_target(backend), updates).register(FastMCPSink(mcp))

    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        await client.call_tool("update_set_name", {"id": 1, "name": "X"})

    assert captured["sql"].startswith("UPDATE customers ")


@pytest.mark.asyncio
async def test_schema_nonempty_generates_qualified_table(
    sqlite_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = sqlite_backend(sqlite_db)
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
    UpdateTools(*single_target(backend), updates).register(FastMCPSink(mcp))

    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        await client.call_tool("update_set_name", {"id": 1, "name": "Y"})

    assert "UPDATE main.customers " in captured["sql"]
