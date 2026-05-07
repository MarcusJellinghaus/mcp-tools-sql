"""Tests for `mcp_tools_sql.server.run_server`."""

from __future__ import annotations

import argparse
import logging
import re
import sqlite3
from pathlib import Path

import pytest

from mcp_tools_sql.backends.sqlite import SQLiteBackend
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
