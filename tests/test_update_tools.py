"""Tests for registering UpdateTools: names, descriptions, validation, schema.

Calling the registered tools is covered in ``test_update_tools_execution.py``.
"""

from __future__ import annotations

from pathlib import Path

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
from mcp_tools_sql.server import FastMCPSink
from mcp_tools_sql.update_tools import UpdateTools
from mcp_tools_sql.utils.tool_spec import ToolCollector
from tests.target_helpers import single_target


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
    UpdateTools(*single_target(backend), {}).register(FastMCPSink(mcp))

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
    UpdateTools(*single_target(backend), updates).register(FastMCPSink(mcp))

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
        UpdateTools(*single_target(backend), updates).register(FastMCPSink(mcp))


# ---------------------------------------------------------------------------
# Descriptions
# ---------------------------------------------------------------------------


def _set_name(description: str) -> dict[str, UpdateConfig]:
    """Return a ``set_name`` update config with the given description."""
    return {
        "set_name": UpdateConfig(
            description=description,
            table="customers",
            key=UpdateKeyConfig(field="id", type="int"),
            fields=[UpdateFieldConfig(field="name", type="str")],
        )
    }


@pytest.mark.parametrize("description", ["", "  "])
def test_empty_description_falls_back(sqlite_db: Path, description: str) -> None:
    """An empty or whitespace-only description gets the generated fallback."""
    backend = _sqlite_backend(sqlite_db)
    sink = ToolCollector()
    UpdateTools(*single_target(backend), _set_name(description)).register(sink)

    assert len(sink) == 1
    spec = sink.specs[0]
    assert spec.name == "update_set_name"
    assert spec.description == "Run configured update `set_name`."
    assert spec.group == "sql.update"
    assert spec.read_only is False


@pytest.mark.asyncio
async def test_non_empty_description_passes_through_unchanged(
    sqlite_db: Path,
) -> None:
    """A description with surrounding whitespace is never stripped."""
    backend = _sqlite_backend(sqlite_db)
    raw = "Sets the name.\n"

    sink = ToolCollector()
    UpdateTools(*single_target(backend), _set_name(raw)).register(sink)
    assert sink.specs[0].description == raw

    mcp = FastMCP("test-raw-description")
    UpdateTools(*single_target(backend), _set_name(raw)).register(FastMCPSink(mcp))
    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        result = await client.list_tools()
        (tool,) = result.tools
        assert tool.description == raw


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
        UpdateTools(*single_target(backend), updates).register(FastMCPSink(mcp))
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
        UpdateTools(*single_target(backend), updates).register(FastMCPSink(mcp))
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
    UpdateTools(*single_target(backend), updates).register(FastMCPSink(mcp))


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
        UpdateTools(*single_target(backend), updates).register(FastMCPSink(mcp))
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
        UpdateTools(*single_target(backend), updates).register(FastMCPSink(mcp))
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
        UpdateTools(*single_target(backend), updates).register(FastMCPSink(mcp))


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
    UpdateTools(*single_target(backend), updates).register(FastMCPSink(mcp))

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
    UpdateTools(*single_target(backend), updates).register(FastMCPSink(mcp))

    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        result = await client.list_tools()
        tool = next(t for t in result.tools if t.name == "update_set_status")
        required = tool.inputSchema.get("required", [])
        assert "status" in required


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
    QueryTools(*single_target(backend), queries).register(FastMCPSink(mcp))
    UpdateTools(*single_target(backend), updates).register(FastMCPSink(mcp))

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
        UpdateTools(*single_target(backend), updates).register(FastMCPSink(mcp))
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
        UpdateTools(*single_target(backend), updates).register(FastMCPSink(mcp))
    assert str(exc.value) == identifier_error("bad-table", "set_name")
