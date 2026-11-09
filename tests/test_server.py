"""Tests for `mcp_tools_sql.server`."""

from __future__ import annotations

import argparse
import logging
import re
import sqlite3
import warnings
from pathlib import Path
from typing import Any

import pytest
from pydantic.json_schema import PydanticJsonSchemaWarning

from mcp_tools_sql import toolset as toolset_module
from mcp_tools_sql.backends.registry import BackendRegistry
from mcp_tools_sql.backends.sqlite import SQLiteBackend
from mcp_tools_sql.config.loader import (
    load_database_config,
    load_query_config,
    resolve_targets,
)
from mcp_tools_sql.schema_tools import (
    PROGRAMMATIC_BUILTIN_TOOLS,
    load_default_queries,
)
from mcp_tools_sql.server import (
    FastMCPSink,
    ToolServer,
    build_tool_server,
    run_server,
)
from mcp_tools_sql.toolset import SqlToolset, assemble_toolset


def _write_sqlite_configs(tmp_path: Path) -> argparse.Namespace:
    """Create a SQLite project + database config and return parsed args."""
    db = tmp_path / "test.db"
    sqlite3.connect(str(db)).close()
    qcfg = tmp_path / "mcp-tools-sql.toml"
    qcfg.write_text('connection = "default"\n')
    dbcfg = tmp_path / "db.toml"
    dbcfg.write_text(
        f'[connections.default]\nbackend = "sqlite"\npath = "{db.as_posix()}"\n'
    )
    return argparse.Namespace(
        config=qcfg,
        database_config=dbcfg,
        log_level="INFO",
    )


def _make_server(args: argparse.Namespace, allow_updates: bool) -> ToolServer:
    """Build a registered ToolServer from the configs named in ``args``."""
    qcfg = load_query_config(args.config)
    dbcfg = load_database_config(args.database_config)
    targets = resolve_targets(qcfg, dbcfg)
    return ToolServer(assemble_toolset(qcfg, targets, BackendRegistry(), allow_updates))


def _counting_close_all(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    """Patch `BackendRegistry.close_all` to count calls; return the counter."""
    close_called = {"n": 0}
    original_close_all = BackendRegistry.close_all

    def counting_close_all(self: BackendRegistry) -> None:
        close_called["n"] += 1
        original_close_all(self)

    monkeypatch.setattr(BackendRegistry, "close_all", counting_close_all)
    return close_called


async def _tool_names(server: ToolServer) -> set[str]:
    """Return the tool names the MCP client sees on ``server``."""
    from mcp.shared.memory import create_connected_server_and_client_session

    async with create_connected_server_and_client_session(
        server.mcp, raise_exceptions=True
    ) as client:
        result = await client.list_tools()
        return {t.name for t in result.tools}


def test_run_server_smoke_calls_run_and_closes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`run_server` returns None and always calls `registry.close_all()`."""
    args = _write_sqlite_configs(tmp_path)

    run_called = {"n": 0}

    def fake_run(self: ToolServer) -> None:
        run_called["n"] += 1

    monkeypatch.setattr(ToolServer, "run", fake_run)
    close_called = _counting_close_all(monkeypatch)

    run_server(args)
    assert run_called["n"] == 1
    assert close_called["n"] == 1


def test_keyboard_interrupt_runs_close(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """KeyboardInterrupt from `run()` propagates and calls `registry.close_all()`."""
    args = _write_sqlite_configs(tmp_path)

    def fake_run(self: ToolServer) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(ToolServer, "run", fake_run)
    close_called = _counting_close_all(monkeypatch)

    with pytest.raises(KeyboardInterrupt):
        run_server(args)
    assert close_called["n"] == 1


def test_pre_mcp_run_value_error_for_bad_config(tmp_path: Path) -> None:
    """A non-existent --config path raises ValueError before mcp.run()."""
    missing = tmp_path / "missing.toml"
    args = argparse.Namespace(
        config=missing,
        database_config=None,
        log_level="INFO",
    )
    with pytest.raises(ValueError, match="Config not found"):
        run_server(args)


def test_lazy_connect_constructible_when_db_unreachable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Server constructs successfully even when the DB is unreachable."""
    bad_db = tmp_path / "missing_subdir" / "test.db"
    qcfg = tmp_path / "mcp-tools-sql.toml"
    qcfg.write_text('connection = "default"\n')
    dbcfg = tmp_path / "db.toml"
    dbcfg.write_text(
        f'[connections.default]\nbackend = "sqlite"\npath = "{bad_db.as_posix()}"\n'
    )
    args = argparse.Namespace(
        config=qcfg,
        database_config=dbcfg,
        log_level="INFO",
    )

    connect_called = {"n": 0}

    def fake_connect(self: SQLiteBackend) -> None:
        connect_called["n"] += 1

    monkeypatch.setattr(SQLiteBackend, "connect", fake_connect)
    monkeypatch.setattr(ToolServer, "run", lambda self: None)

    run_server(args)
    assert connect_called["n"] == 0


def test_startup_info_log_line(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Startup emits one INFO record describing backend/connection/builtin tools."""
    args = _write_sqlite_configs(tmp_path)
    monkeypatch.setattr(ToolServer, "run", lambda self: None)

    with caplog.at_level(logging.INFO, logger="mcp_tools_sql.server"):
        run_server(args)

    matching = [
        rec
        for rec in caplog.records
        if rec.name == "mcp_tools_sql.server"
        and rec.levelno == logging.INFO
        and re.search(
            r"starting MCP server backend=sqlite connection=default "
            r".*builtin_tools=",
            rec.getMessage(),
        )
    ]
    assert len(matching) == 1


def test_startup_log_reports_connection_and_database_counts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Startup log reports single connection/database counts for a lone target."""
    args = _write_sqlite_configs(tmp_path)
    monkeypatch.setattr(ToolServer, "run", lambda self: None)

    with caplog.at_level(logging.INFO, logger="mcp_tools_sql.server"):
        run_server(args)

    matching = [
        rec
        for rec in caplog.records
        if rec.name == "mcp_tools_sql.server"
        and rec.levelno == logging.INFO
        and re.search(r"connections=1 databases=1", rec.getMessage())
    ]
    assert len(matching) == 1


@pytest.mark.asyncio
async def test_configured_query_registered_as_tool(tmp_path: Path) -> None:
    """A configured `[queries.foo]` entry registers as `query_foo` on the server."""
    db = tmp_path / "test.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO customers VALUES (1, 'Alice')")
    conn.commit()
    conn.close()

    qcfg_path = tmp_path / "mcp-tools-sql.toml"
    qcfg_path.write_text(
        'connection = "default"\n'
        "\n"
        "[queries.foo]\n"
        'description = "Foo query"\n'
        'sql = "SELECT * FROM customers"\n'
        "\n"
        "[queries.foo.backends.sqlite]\n"
        'sql = "SELECT * FROM customers"\n'
    )
    dbcfg_path = tmp_path / "db.toml"
    dbcfg_path.write_text(
        f'[connections.default]\nbackend = "sqlite"\npath = "{db.as_posix()}"\n'
    )
    args = argparse.Namespace(config=qcfg_path, database_config=dbcfg_path)

    server = _make_server(args, allow_updates=True)
    try:
        names = await _tool_names(server)
        assert "query_foo" in names
        assert {
            "read_schemas",
            "read_tables",
            "read_columns",
            "read_relations",
        }.issubset(names)
    finally:
        server.close()


@pytest.mark.asyncio
async def test_write_query_not_registered_even_with_allow_updates(
    tmp_path: Path,
) -> None:
    """The read-only gate is unconditional: allow_updates does not unlock it."""
    db = tmp_path / "test.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE Orders (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

    qcfg_path = tmp_path / "mcp-tools-sql.toml"
    qcfg_path.write_text(
        'connection = "default"\n'
        "\n"
        "[queries.purge]\n"
        'description = "Purge orders"\n'
        'sql = "DELETE FROM Orders"\n'
    )
    dbcfg_path = tmp_path / "db.toml"
    dbcfg_path.write_text(
        f'[connections.default]\nbackend = "sqlite"\npath = "{db.as_posix()}"\n'
    )
    args = argparse.Namespace(config=qcfg_path, database_config=dbcfg_path)

    server = _make_server(args, allow_updates=True)
    try:
        assert "query_purge" not in await _tool_names(server)
    finally:
        server.close()


@pytest.mark.asyncio
async def test_validate_sql_registered_as_builtin_tool(tmp_path: Path) -> None:
    """The constructor registers the builtin `validate_sql` on the MCP server."""
    server = _make_server(_write_sqlite_configs(tmp_path), allow_updates=False)
    try:
        assert "validate_sql" in await _tool_names(server)
    finally:
        server.close()


@pytest.mark.asyncio
async def test_count_records_registered_as_builtin_tool(tmp_path: Path) -> None:
    """The constructor registers the builtin `count_records` on the MCP server."""
    server = _make_server(_write_sqlite_configs(tmp_path), allow_updates=False)
    try:
        assert "count_records" in await _tool_names(server)
    finally:
        server.close()


def test_startup_builtin_tools_counter_includes_programmatic_builtins(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """`builtin_tools=N` counter equals TOML count + programmatic builtin count."""
    args = _write_sqlite_configs(tmp_path)
    monkeypatch.setattr(ToolServer, "run", lambda self: None)

    expected = len(load_default_queries()) + len(PROGRAMMATIC_BUILTIN_TOOLS)

    with caplog.at_level(logging.INFO, logger="mcp_tools_sql.server"):
        run_server(args)

    matching = [
        rec
        for rec in caplog.records
        if rec.name == "mcp_tools_sql.server"
        and rec.levelno == logging.INFO
        and re.search(rf"builtin_tools={expected}\b", rec.getMessage())
    ]
    assert len(matching) == 1


def _write_multi_sqlite_configs(tmp_path: Path) -> argparse.Namespace:
    """Create two SQLite connections (two targets) and return parsed args."""
    db_a = tmp_path / "a.db"
    db_b = tmp_path / "b.db"
    sqlite3.connect(str(db_a)).close()
    sqlite3.connect(str(db_b)).close()
    qcfg = tmp_path / "mcp-tools-sql.toml"
    qcfg.write_text('connection = "default"\n')
    dbcfg = tmp_path / "db.toml"
    dbcfg.write_text(
        f'[connections.default]\nbackend = "sqlite"\npath = "{db_a.as_posix()}"\n'
        'description = "Primary"\n'
        f'\n[connections.second]\nbackend = "sqlite"\npath = "{db_b.as_posix()}"\n'
        'description = "Secondary"\n'
    )
    return argparse.Namespace(
        config=qcfg,
        database_config=dbcfg,
        log_level="INFO",
    )


@pytest.mark.asyncio
async def test_read_databases_not_registered_for_single_target(
    tmp_path: Path,
) -> None:
    """With one target, ``read_databases`` is not registered."""
    server = _make_server(_write_sqlite_configs(tmp_path), allow_updates=False)
    try:
        assert "read_databases" not in await _tool_names(server)
    finally:
        server.close()


@pytest.mark.asyncio
async def test_read_databases_registered_and_lists_targets_when_multi(
    tmp_path: Path,
) -> None:
    """With >1 target, ``read_databases`` is registered and lists every target."""
    from mcp.shared.memory import create_connected_server_and_client_session

    server = _make_server(_write_multi_sqlite_configs(tmp_path), allow_updates=False)
    try:
        async with create_connected_server_and_client_session(
            server.mcp, raise_exceptions=True
        ) as client:
            result = await client.list_tools()
            names = {t.name for t in result.tools}
            assert "read_databases" in names

            call = await client.call_tool("read_databases", {})
            text = call.content[0].text  # type: ignore[union-attr]
            assert "default" in text
            assert "second" in text
            # Default connection's target is flagged; the other is not.
            assert "True" in text
            assert "False" in text
    finally:
        server.close()


_UPDATE_SET_NAME = (
    "\n[updates.set_name]\n"
    'description = "Set customer name"\n'
    'table = "customers"\n'
    "\n[updates.set_name.key]\n"
    'field = "id"\n'
    'type = "int"\n'
    "\n[[updates.set_name.fields]]\n"
    'field = "name"\n'
    'type = "str"\n'
)


def _write_update_configs(tmp_path: Path, allow_updates: bool) -> argparse.Namespace:
    """Create configs with an [updates.set_name] entry and given allow_updates."""
    db = tmp_path / "test.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT)")
    conn.commit()
    conn.close()

    qcfg = tmp_path / "mcp-tools-sql.toml"
    qcfg.write_text('connection = "default"\n' + _UPDATE_SET_NAME)
    dbcfg = tmp_path / "db.toml"
    dbcfg.write_text(
        f'[connections.default]\nbackend = "sqlite"\npath = "{db.as_posix()}"\n'
        f"\n[security]\nallow_updates = {str(allow_updates).lower()}\n"
    )
    return argparse.Namespace(
        config=qcfg,
        database_config=dbcfg,
        log_level="INFO",
    )


@pytest.mark.asyncio
async def test_update_tool_registered_when_allow_updates_true(tmp_path: Path) -> None:
    """When ``allow_updates=True``, configured updates appear as ``update_*`` tools."""
    server = _make_server(
        _write_update_configs(tmp_path, allow_updates=True), allow_updates=True
    )
    try:
        assert "update_set_name" in await _tool_names(server)
    finally:
        server.close()


@pytest.mark.asyncio
async def test_update_tool_not_registered_when_allow_updates_false(
    tmp_path: Path,
) -> None:
    """``allow_updates=False`` skips update registration; non-update tools unchanged."""
    args = _write_update_configs(tmp_path, allow_updates=False)

    async def _names(allow: bool) -> set[str]:
        server = _make_server(args, allow_updates=allow)
        try:
            return await _tool_names(server)
        finally:
            server.close()

    names_true = await _names(True)
    names_false = await _names(False)

    assert not any(n.startswith("update_") for n in names_false)
    assert {n for n in names_true if not n.startswith("update_")} == {
        n for n in names_false if not n.startswith("update_")
    }


def test_run_server_reads_allow_updates_from_database_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``run_server`` reads ``dbcfg.security.allow_updates`` and forwards it."""
    args = _write_update_configs(tmp_path, allow_updates=False)

    recorded: dict[str, bool] = {}
    original = toolset_module.assemble_toolset

    def recording_assemble(*a: Any, **kw: Any) -> SqlToolset:
        recorded["allow_updates"] = a[3]
        return original(*a, **kw)

    monkeypatch.setattr(toolset_module, "assemble_toolset", recording_assemble)
    monkeypatch.setattr(ToolServer, "run", lambda self: None)

    run_server(args)
    assert recorded["allow_updates"] is False


@pytest.mark.asyncio
async def test_constructor_registers_builtin_and_configured_tools(
    tmp_path: Path,
) -> None:
    """`ToolServer(toolset)` registers both builtin and configured tools."""
    server = _make_server(
        _write_update_configs(tmp_path, allow_updates=True), allow_updates=True
    )
    try:
        names = await _tool_names(server)
        assert "read_tables" in names
        assert "validate_sql" in names
        assert "update_set_name" in names
    finally:
        server.close()


def test_build_tool_server_registers_tools(tmp_path: Path) -> None:
    """`build_tool_server` returns a server whose tools are already registered."""
    args = _write_sqlite_configs(tmp_path)
    server, qpath = build_tool_server(args)
    try:
        assert server.mcp._tool_manager.list_tools() != []  # pylint: disable=protected-access
        assert qpath == args.config
    finally:
        server.close()


def test_build_tool_server_raises_for_unknown_connection(tmp_path: Path) -> None:
    """The eager build surfaces a query pinned to an unknown connection."""
    args = _write_sqlite_configs(tmp_path)
    args.config.write_text(
        'connection = "default"\n'
        "\n[queries.bad]\n"
        'description = "Pinned to an unknown connection"\n'
        'connection = "nope"\n'
        'sql = "SELECT 1"\n'
    )
    with pytest.raises(ValueError):
        build_tool_server(args)


def test_build_tool_server_closes_toolset_when_registration_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failure inside `ToolServer(toolset)` closes the toolset and re-raises."""
    args = _write_sqlite_configs(tmp_path)
    close_called = _counting_close_all(monkeypatch)

    def failing_add(self: FastMCPSink, spec: object) -> None:
        raise RuntimeError("registration failed")

    monkeypatch.setattr(FastMCPSink, "add", failing_add)

    with pytest.raises(RuntimeError, match="registration failed"):
        build_tool_server(args)
    assert close_called["n"] == 1


def test_toolset_is_hashable(tmp_path: Path) -> None:
    """`SqlToolset` uses identity semantics, so it can live in a set."""
    args = _write_sqlite_configs(tmp_path)
    qcfg = load_query_config(args.config)
    dbcfg = load_database_config(args.database_config)
    targets = resolve_targets(qcfg, dbcfg)
    with assemble_toolset(qcfg, targets, BackendRegistry(), False) as toolset:
        assert toolset in {toolset}


def test_close_delegates_to_registry_close_all(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`ToolServer.close()` calls `registry.close_all()` exactly once."""
    server = _make_server(_write_sqlite_configs(tmp_path), allow_updates=False)
    close_called = _counting_close_all(monkeypatch)

    server.close()
    assert close_called["n"] == 1


def test_run_server_closes_exactly_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`run_server` closes the toolset exactly once after a clean run."""
    args = _write_sqlite_configs(tmp_path)
    monkeypatch.setattr(ToolServer, "run", lambda self: None)
    close_called = _counting_close_all(monkeypatch)

    run_server(args)
    assert close_called["n"] == 1


def test_toolset_property_exposes_constructor_value(tmp_path: Path) -> None:
    """`server.toolset` is the exact toolset passed to the constructor."""
    args = _write_sqlite_configs(tmp_path)
    qcfg = load_query_config(args.config)
    dbcfg = load_database_config(args.database_config)
    targets = resolve_targets(qcfg, dbcfg)
    toolset = assemble_toolset(qcfg, targets, BackendRegistry(), False)
    server = ToolServer(toolset)
    try:
        assert server.toolset is toolset
    finally:
        server.close()


@pytest.mark.asyncio
async def test_mcp_tools_match_specs(tmp_path: Path) -> None:
    """MCP names, descriptions and param descriptions equal the specs'."""
    from mcp.shared.memory import create_connected_server_and_client_session

    args = _write_multi_sqlite_configs(tmp_path)
    for db in ("a.db", "b.db"):
        conn = sqlite3.connect(str(tmp_path / db))
        conn.execute("CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT)")
        conn.commit()
        conn.close()
    args.config.write_text(
        'connection = "default"\n'
        "\n[queries.foo]\n"
        'description = "Foo query"\n'
        'sql = "SELECT * FROM customers"\n' + _UPDATE_SET_NAME
    )
    server = _make_server(args, allow_updates=True)
    specs = {spec.name: spec for spec in server.toolset.specs}
    assert {"query_foo", "update_set_name", "read_databases"} <= specs.keys()
    try:
        async with create_connected_server_and_client_session(
            server.mcp, raise_exceptions=True
        ) as client:
            tools = (await client.list_tools()).tools
        assert {t.name for t in tools} == specs.keys()
        for tool in tools:
            spec = specs[tool.name]
            assert tool.description == spec.description
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", PydanticJsonSchemaWarning)
                spec_props = spec.args_model.model_json_schema().get("properties", {})
            mcp_props = tool.inputSchema.get("properties", {})
            assert mcp_props.keys() == spec_props.keys(), tool.name
            for param, schema in mcp_props.items():
                assert schema.get("description") == spec_props[param].get(
                    "description"
                ), f"{tool.name}.{param}"
    finally:
        server.close()
