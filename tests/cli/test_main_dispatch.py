"""Tests for `mcp_tools_sql.main` argparse + dispatch behavior."""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from mcp_tools_sql.cli.commands import init as init_cmd
from mcp_tools_sql.cli.commands import verify as verify_cmd
from mcp_tools_sql.main import _build_parser, main


def test_dispatch_init_calls_init_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """`mcp-tools-sql init --backend sqlite` dispatches to init.run."""
    captured: dict[str, Any] = {}

    def fake_run(args: argparse.Namespace) -> int:
        captured["args"] = args
        return 0

    monkeypatch.setattr(init_cmd, "run", fake_run)

    rc = main(["init", "--backend", "sqlite"])
    assert rc == 0
    assert captured["args"].command == "init"
    assert captured["args"].backend == "sqlite"


def test_dispatch_verify_calls_verify_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """`mcp-tools-sql verify` dispatches to verify.run."""
    captured: dict[str, Any] = {}

    def fake_run(args: argparse.Namespace) -> int:
        captured["args"] = args
        return 0

    monkeypatch.setattr(verify_cmd, "run", fake_run)

    rc = main(["verify"])
    assert rc == 0
    assert captured["args"].command == "verify"


def test_database_config_flag_parsed() -> None:
    """`--database-config foo` parses into Path('foo')."""
    parser = _build_parser()
    args = parser.parse_args(["--database-config", "foo", "verify"])
    assert args.database_config == Path("foo")


def test_config_flag_parsed() -> None:
    """`--config bar.toml` parses into Path('bar.toml')."""
    parser = _build_parser()
    args = parser.parse_args(["--config", "bar.toml", "verify"])
    assert args.config == Path("bar.toml")


def test_no_command_defaults_to_server() -> None:
    """No subcommand → args.command is None (main() defaults to server)."""
    parser = _build_parser()
    args = parser.parse_args([])
    assert args.command is None


def test_no_command_dispatches_to_server(monkeypatch: pytest.MonkeyPatch) -> None:
    """`mcp-tools-sql` (no args) dispatches to run_server and exits 0."""
    called = {"n": 0}

    def fake(args: argparse.Namespace) -> None:
        called["n"] += 1

    monkeypatch.setattr("mcp_tools_sql.main.run_server", fake)
    rc = main([])
    assert rc == 0
    assert called["n"] == 1


def test_server_command_dispatches_to_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`mcp-tools-sql server` dispatches to run_server and exits 0."""
    called = {"n": 0}

    def fake(args: argparse.Namespace) -> None:
        called["n"] += 1

    monkeypatch.setattr("mcp_tools_sql.main.run_server", fake)
    rc = main(["server"])
    assert rc == 0
    assert called["n"] == 1


def _build_failing_args(tmp_path: Path, scenario: str) -> list[str]:
    """Build CLI args producing a pre-mcp.run failure for `scenario`."""
    if scenario == "missing_config":
        return ["--config", str(tmp_path / "missing.toml"), "server"]
    if scenario == "missing_connection_name":
        qcfg = tmp_path / "mcp-tools-sql.toml"
        qcfg.write_text('connection = "nonexistent"\n')
        dbcfg = tmp_path / "db.toml"
        dbcfg.write_text('[connections.other]\nbackend = "sqlite"\npath = "x.db"\n')
        return [
            "--config",
            str(qcfg),
            "--database-config",
            str(dbcfg),
            "server",
        ]
    if scenario == "unknown_backend":
        db = tmp_path / "test.db"
        sqlite3.connect(str(db)).close()
        qcfg = tmp_path / "mcp-tools-sql.toml"
        qcfg.write_text('connection = "default"\n')
        dbcfg = tmp_path / "db.toml"
        dbcfg.write_text(
            f'[connections.default]\nbackend = "bogus"\npath = "{db.as_posix()}"\n'
        )
        return [
            "--config",
            str(qcfg),
            "--database-config",
            str(dbcfg),
            "server",
        ]
    raise AssertionError(f"unknown scenario: {scenario}")


@pytest.mark.parametrize(
    "scenario",
    ["missing_config", "missing_connection_name", "unknown_backend"],
)
def test_server_friendly_error_for_bad_config_returns_2(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    scenario: str,
) -> None:
    """Bad configs produce exit 2 with a friendly stderr hint and no traceback."""
    argv = _build_failing_args(tmp_path, scenario)
    rc = main(argv)
    captured = capsys.readouterr()
    assert rc == 2
    assert "Error:" in captured.err
    assert "verify" in captured.err
    assert "Traceback" not in captured.err


def test_server_keyboard_interrupt_returns_130(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """KeyboardInterrupt from run_server is translated to exit code 130."""

    def fake(args: argparse.Namespace) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr("mcp_tools_sql.main.run_server", fake)
    rc = main(["server"])
    assert rc == 130


def test_help_subcommand_still_prints_help(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`mcp-tools-sql help` continues to print help and return 0."""
    rc = main(["help"])
    captured = capsys.readouterr()
    assert rc == 0
    assert "usage: mcp-tools-sql" in captured.out


def test_setup_logging_runs_before_run_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`setup_logging` must be invoked before `run_server` on the server path."""
    order: list[str] = []

    def fake_setup(*_args: Any, **_kwargs: Any) -> None:
        order.append("setup_logging")

    def fake_run(args: argparse.Namespace) -> None:
        order.append("run_server")

    monkeypatch.setattr("mcp_tools_sql.main.setup_logging", fake_setup)
    monkeypatch.setattr("mcp_tools_sql.main.run_server", fake_run)

    rc = main(["server"])
    assert rc == 0
    assert order == ["setup_logging", "run_server"]


def test_init_subparser_requires_backend() -> None:
    """`init` without --backend exits via argparse SystemExit."""
    parser = _build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["init"])


def test_init_subparser_rejects_unknown_backend() -> None:
    """`init --backend bogus` is rejected by argparse."""
    parser = _build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["init", "--backend", "bogus"])
