"""Tests for `mcp_tools_sql.main` argparse + dispatch behavior."""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from mcp_tools_sql.cli.commands import init as init_cmd
from mcp_tools_sql.cli.commands import verify as verify_cmd
from mcp_tools_sql.main import (
    _build_parser,
    _resolve_log_file,
    _resolve_log_level,
    main,
)
from mcp_tools_sql.utils.log_utils import OUTPUT


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
    caplog: pytest.LogCaptureFixture,
    scenario: str,
) -> None:
    """Bad configs produce exit 2 with a friendly logged hint and no traceback."""
    caplog.set_level(OUTPUT)
    argv = _build_failing_args(tmp_path, scenario)
    rc = main(argv)
    captured = capsys.readouterr()
    messages = [rec.getMessage() for rec in caplog.records]
    levels = {rec.levelname for rec in caplog.records}
    assert rc == 2
    assert "ERROR" in levels  # the exception text
    assert any("verify" in msg for msg in messages)  # the OUTPUT hint
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


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        ([], "INFO"),  # bare -> server
        (["server"], "INFO"),
        (["init", "--backend", "sqlite"], "OUTPUT"),
        (["verify"], "OUTPUT"),
        (["--log-level", "DEBUG", "server"], "DEBUG"),  # explicit wins
        (["--log-level", "DEBUG", "verify"], "DEBUG"),
        (["--log-level", "OUTPUT", "server"], "OUTPUT"),  # new choice accepted
    ],
)
def test_resolve_log_level(argv: list[str], expected: str) -> None:
    """The resolved level honours an explicit flag, else the per-command default."""
    args = _build_parser().parse_args(argv)
    assert _resolve_log_level(args, args.command or "server") == expected


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (["--console-only", "server"], None),
        (["--log-file", "x.log", "server"], "x.log"),
        (["--console-only", "--log-file", "x.log", "server"], None),  # console wins
        (["init", "--backend", "sqlite"], None),
        (["verify"], None),
        (["--log-file", "x.log", "verify"], "x.log"),
    ],
)
def test_resolve_log_file(argv: list[str], expected: str | None) -> None:
    """--console-only wins, an explicit file is honoured, non-server has no default."""
    args = _build_parser().parse_args(argv)
    assert _resolve_log_file(args, args.command or "server") == expected


def test_resolve_log_file_server_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`server` defaults to a timestamped file under ~/.mcp-tools-sql/logs/."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    args = _build_parser().parse_args(["server"])
    result = _resolve_log_file(args, "server")
    assert result is not None
    resolved = Path(result)
    assert resolved.parent == tmp_path / ".mcp-tools-sql" / "logs"
    assert resolved.name.startswith("mcp_tools_sql_")
    assert resolved.name.endswith(".log")
    assert not resolved.exists()  # helper is pure: it creates nothing


@pytest.mark.parametrize(
    ("argv", "expect_file", "expected_console_level", "expected_log_level"),
    [
        (["server"], True, OUTPUT, "INFO"),
        (["--console-only", "server"], False, None, "INFO"),  # guards the conditional
        (["verify"], False, None, "OUTPUT"),  # non-server stays console-only
    ],
)
def test_setup_logging_arguments(
    argv: list[str],
    expect_file: bool,
    expected_console_level: int | None,
    expected_log_level: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`setup_logging` receives the per-command file and console thresholds."""
    recorded: dict[str, Any] = {}

    def fake_setup(
        log_level: str, log_file: str | None = None, console_level: int | None = None
    ) -> None:
        recorded.update(
            log_level=log_level, log_file=log_file, console_level=console_level
        )

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr("mcp_tools_sql.main.setup_logging", fake_setup)
    monkeypatch.setattr("mcp_tools_sql.main.run_server", lambda args: None)
    monkeypatch.setattr(verify_cmd, "run", lambda args: 0)

    assert main(argv) == 0
    assert (recorded["log_file"] is not None) is expect_file
    assert recorded["console_level"] == expected_console_level
    assert recorded["log_level"] == expected_log_level


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
