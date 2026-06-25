"""Tests for `mcp_tools_sql.server.run_server`."""

from __future__ import annotations

import argparse
import logging
import re
import sqlite3
from pathlib import Path

import pytest

from mcp_tools_sql.backends.base import create_backend
from mcp_tools_sql.backends.sqlite import SQLiteBackend
from mcp_tools_sql.config.loader import (
    load_database_config,
    load_query_config,
    resolve_connection,
)
from mcp_tools_sql.schema_tools import (
    PROGRAMMATIC_BUILTIN_TOOLS,
    load_default_queries,
)
from mcp_tools_sql.server import ToolServer, run_server


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


def test_run_server_smoke_calls_run_and_closes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`run_server` returns None and always calls `backend.close()`."""
    args = _write_sqlite_configs(tmp_path)

    run_called = {"n": 0}

    def fake_run(self: ToolServer) -> None:
        run_called["n"] += 1

    monkeypatch.setattr(ToolServer, "run", fake_run)

    close_called = {"n": 0}
    original_close = SQLiteBackend.close

    def counting_close(self: SQLiteBackend) -> None:
        close_called["n"] += 1
        original_close(self)

    monkeypatch.setattr(SQLiteBackend, "close", counting_close)

    run_server(args)
    assert run_called["n"] == 1
    assert close_called["n"] == 1


def test_keyboard_interrupt_runs_close(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """KeyboardInterrupt from `mcp.run()` propagates and closes the backend."""
    args = _write_sqlite_configs(tmp_path)

    def fake_run(self: ToolServer) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(ToolServer, "run", fake_run)

    close_called = {"n": 0}
    original_close = SQLiteBackend.close

    def counting_close(self: SQLiteBackend) -> None:
        close_called["n"] += 1
        original_close(self)

    monkeypatch.setattr(SQLiteBackend, "close", counting_close)

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


@pytest.mark.asyncio
async def test_configured_query_registered_as_tool(tmp_path: Path) -> None:
    """A configured `[queries.foo]` entry registers as `query_foo` on the server."""
    from mcp.shared.memory import create_connected_server_and_client_session

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

    qcfg = load_query_config(qcfg_path)
    dbcfg = load_database_config(dbcfg_path)
    conn_cfg = resolve_connection(qcfg, dbcfg)
    backend = create_backend(conn_cfg)
    server = ToolServer(qcfg, backend, conn_cfg.backend, allow_updates=True)
    server._register_builtin_tools()  # pylint: disable=protected-access
    server._register_configured_tools()  # pylint: disable=protected-access

    try:
        async with create_connected_server_and_client_session(
            server.mcp, raise_exceptions=True
        ) as client:
            result = await client.list_tools()
            names = {t.name for t in result.tools}
            assert "query_foo" in names
            assert {
                "read_schemas",
                "read_tables",
                "read_columns",
                "read_relations",
            }.issubset(names)
    finally:
        backend.close()


@pytest.mark.asyncio
async def test_validate_sql_registered_as_builtin_tool(tmp_path: Path) -> None:
    """`_register_builtin_tools()` registers `validate_sql` on the MCP server."""
    from mcp.shared.memory import create_connected_server_and_client_session

    args = _write_sqlite_configs(tmp_path)
    qcfg = load_query_config(args.config)
    dbcfg = load_database_config(args.database_config)
    conn_cfg = resolve_connection(qcfg, dbcfg)
    backend = create_backend(conn_cfg)
    server = ToolServer(qcfg, backend, conn_cfg.backend, allow_updates=False)
    server._register_builtin_tools()  # pylint: disable=protected-access

    try:
        async with create_connected_server_and_client_session(
            server.mcp, raise_exceptions=True
        ) as client:
            result = await client.list_tools()
            names = {t.name for t in result.tools}
            assert "validate_sql" in names
    finally:
        backend.close()


@pytest.mark.asyncio
async def test_count_records_registered_as_builtin_tool(tmp_path: Path) -> None:
    """`_register_builtin_tools()` registers `count_records` on the MCP server."""
    from mcp.shared.memory import create_connected_server_and_client_session

    args = _write_sqlite_configs(tmp_path)
    qcfg = load_query_config(args.config)
    dbcfg = load_database_config(args.database_config)
    conn_cfg = resolve_connection(qcfg, dbcfg)
    backend = create_backend(conn_cfg)
    server = ToolServer(qcfg, backend, conn_cfg.backend, allow_updates=False)
    server._register_builtin_tools()  # pylint: disable=protected-access

    try:
        async with create_connected_server_and_client_session(
            server.mcp, raise_exceptions=True
        ) as client:
            result = await client.list_tools()
            names = {t.name for t in result.tools}
            assert "count_records" in names
    finally:
        backend.close()


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


def _write_update_configs(tmp_path: Path, allow_updates: bool) -> argparse.Namespace:
    """Create configs with an [updates.set_name] entry and given allow_updates."""
    db = tmp_path / "test.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT)")
    conn.commit()
    conn.close()

    qcfg = tmp_path / "mcp-tools-sql.toml"
    qcfg.write_text(
        'connection = "default"\n'
        "\n"
        "[updates.set_name]\n"
        'description = "Set customer name"\n'
        'table = "customers"\n'
        "\n"
        "[updates.set_name.key]\n"
        'field = "id"\n'
        'type = "int"\n'
        "\n"
        "[[updates.set_name.fields]]\n"
        'field = "name"\n'
        'type = "str"\n'
    )
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
    from mcp.shared.memory import create_connected_server_and_client_session

    args = _write_update_configs(tmp_path, allow_updates=True)
    qcfg = load_query_config(args.config)
    dbcfg = load_database_config(args.database_config)
    conn_cfg = resolve_connection(qcfg, dbcfg)
    backend = create_backend(conn_cfg)
    server = ToolServer(qcfg, backend, conn_cfg.backend, allow_updates=True)
    server._register_configured_tools()  # pylint: disable=protected-access

    try:
        async with create_connected_server_and_client_session(
            server.mcp, raise_exceptions=True
        ) as client:
            result = await client.list_tools()
            names = {t.name for t in result.tools}
            assert "update_set_name" in names
    finally:
        backend.close()


@pytest.mark.asyncio
async def test_update_tool_not_registered_when_allow_updates_false(
    tmp_path: Path,
) -> None:
    """``allow_updates=False`` skips update registration; non-update tools unchanged."""
    from mcp.shared.memory import create_connected_server_and_client_session

    args = _write_update_configs(tmp_path, allow_updates=False)
    qcfg = load_query_config(args.config)
    dbcfg = load_database_config(args.database_config)
    conn_cfg = resolve_connection(qcfg, dbcfg)

    async def _names(allow: bool) -> set[str]:
        backend = create_backend(conn_cfg)
        server = ToolServer(qcfg, backend, conn_cfg.backend, allow_updates=allow)
        server._register_builtin_tools()  # pylint: disable=protected-access
        server._register_configured_tools()  # pylint: disable=protected-access
        try:
            async with create_connected_server_and_client_session(
                server.mcp, raise_exceptions=True
            ) as client:
                result = await client.list_tools()
                return {t.name for t in result.tools}
        finally:
            backend.close()

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
    original_init = ToolServer.__init__

    def recording_init(
        self: ToolServer,
        config: object,
        backend: object,
        backend_name: str,
        allow_updates: bool,
    ) -> None:
        recorded["allow_updates"] = allow_updates
        original_init(self, config, backend, backend_name, allow_updates)  # type: ignore[arg-type]

    monkeypatch.setattr(ToolServer, "__init__", recording_init)
    monkeypatch.setattr(ToolServer, "run", lambda self: None)

    run_server(args)
    assert recorded["allow_updates"] is False
