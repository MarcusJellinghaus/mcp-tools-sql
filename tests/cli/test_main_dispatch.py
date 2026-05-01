"""Tests for `mcp_tools_sql.main` argparse + dispatch behavior."""

from __future__ import annotations

import argparse
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


def test_no_command_prints_help_and_exits_0(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`mcp-tools-sql` (no args) prints help and returns 0."""
    rc = main([])
    captured = capsys.readouterr()
    assert rc == 0
    assert "usage: mcp-tools-sql" in captured.out


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


def test_init_run_raises_not_implemented() -> None:
    """init.run is a stub for now."""
    args = argparse.Namespace()
    with pytest.raises(NotImplementedError, match="step 4"):
        init_cmd.run(args)


def test_verify_run_raises_not_implemented() -> None:
    """verify.run is a stub for now."""
    args = argparse.Namespace()
    with pytest.raises(NotImplementedError, match="steps 5-9"):
        verify_cmd.run(args)
