"""Tests for the ``verify`` MCP tool registered by :class:`ToolServer`."""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from mcp_tools_sql.backends.registry import BackendRegistry
from mcp_tools_sql.config.loader import (
    load_database_config,
    load_query_config,
    resolve_targets,
)
from mcp_tools_sql.server import ToolServer, build_tool_server
from mcp_tools_sql.toolset import assemble_toolset
from tests.sqlite_fixtures import create_db

_RESTART_FRAGMENT = "the running tools keep the config they were built with"


def _write_configs(tmp_path: Path, *, with_query: bool) -> argparse.Namespace:
    """Create a valid SQLite project + database config and return parsed args."""
    db = create_db(
        tmp_path / "test.db",
        "CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT);"
        "INSERT INTO customers VALUES (1, 'Alice');",
    )

    qcfg = tmp_path / "mcp-tools-sql.toml"
    text = 'connection = "default"\n'
    if with_query:
        text += (
            "\n[queries.foo]\n"
            'description = "Foo query"\n'
            'sql = "SELECT * FROM customers"\n'
        )
    qcfg.write_text(text)
    dbcfg = tmp_path / "db.toml"
    dbcfg.write_text(
        f'[connections.default]\nbackend = "sqlite"\npath = "{db.as_posix()}"\n'
    )
    return argparse.Namespace(config=qcfg, database_config=dbcfg)


async def _tool_names(server: ToolServer) -> set[str]:
    async with create_connected_server_and_client_session(
        server.mcp, raise_exceptions=True
    ) as client:
        result = await client.list_tools()
        return {t.name for t in result.tools}


async def _call_verify(server: ToolServer) -> str:
    async with create_connected_server_and_client_session(
        server.mcp, raise_exceptions=True
    ) as client:
        call = await client.call_tool("verify", {})
        return call.content[0].text  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_verify_listed(tmp_path: Path) -> None:
    """``verify`` is a registered built-in tool."""
    server, _ = build_tool_server(_write_configs(tmp_path, with_query=False))
    try:
        assert "verify" in await _tool_names(server)
    finally:
        server.close()


@pytest.mark.asyncio
async def test_verify_returns_short_summary_and_restart_note(tmp_path: Path) -> None:
    """A valid config yields ``Config loaded.`` plus the restart note."""
    server, _ = build_tool_server(_write_configs(tmp_path, with_query=True))
    try:
        text = await _call_verify(server)
    finally:
        server.close()
    assert text.startswith("Config loaded.")
    assert _RESTART_FRAGMENT in text


@pytest.mark.asyncio
async def test_verify_rereads_disk_and_hides_credentials(tmp_path: Path) -> None:
    """Edits on disk are picked up; a password in the bad config is never shown."""
    args = _write_configs(tmp_path, with_query=False)
    server, _ = build_tool_server(args)
    args.database_config.write_text(
        "[connections.default]\n"
        'backend = "mssql"\n'
        'host = "localhost"\n'
        'database = "a"\n'
        'databases = ["b", "c"]\n'
        'username = "sa"\n'
        'password = "s3cret-pw"\n'
    )
    try:
        text = await _call_verify(server)
    finally:
        server.close()
    assert "Config has errors." in text
    assert "s3cret-pw" not in text
    assert _RESTART_FRAGMENT in text


@pytest.mark.asyncio
async def test_no_builtin_tool_uses_configured_prefixes(tmp_path: Path) -> None:
    """Built-in tool names never start with ``query_`` or ``update_``."""
    server, _ = build_tool_server(_write_configs(tmp_path, with_query=False))
    try:
        names = await _tool_names(server)
    finally:
        server.close()
    assert not [n for n in names if n.startswith(("query_", "update_"))]


@pytest.mark.asyncio
async def test_verify_registered_without_path_kwargs(tmp_path: Path) -> None:
    """Positional construction without path kwargs still registers ``verify``."""
    args = _write_configs(tmp_path, with_query=False)
    qcfg = load_query_config(args.config)
    dbcfg = load_database_config(args.database_config)
    targets = resolve_targets(qcfg, dbcfg)
    server = ToolServer(assemble_toolset(qcfg, targets, BackendRegistry(), False))
    try:
        assert "verify" in await _tool_names(server)
    finally:
        server.close()


@pytest.mark.asyncio
async def test_verify_leaves_server_registry_untouched(tmp_path: Path) -> None:
    """A configured query tool still works after ``verify`` ran."""
    server, _ = build_tool_server(_write_configs(tmp_path, with_query=True))
    try:
        async with create_connected_server_and_client_session(
            server.mcp, raise_exceptions=True
        ) as client:
            await client.call_tool("verify", {})
            call = await client.call_tool("query_foo", {})
            text = call.content[0].text  # type: ignore[union-attr]
    finally:
        server.close()
    assert "Alice" in text
