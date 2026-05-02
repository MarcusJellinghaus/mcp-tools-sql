"""Tests for `--help`, `--version`, and the `help` subcommand."""

from __future__ import annotations

import re

import pytest

from mcp_tools_sql import __version__
from mcp_tools_sql.main import main


def test_top_level_help_exits_0_with_usage(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`mcp-tools-sql --help` exits 0 and lists the subcommands."""
    rc = main(["--help"])
    captured = capsys.readouterr()
    assert rc == 0
    assert "usage: mcp-tools-sql" in captured.out
    assert "init" in captured.out
    assert "verify" in captured.out


def test_init_help_exits_0(capsys: pytest.CaptureFixture[str]) -> None:
    """`mcp-tools-sql init --help` exits 0 and mentions --backend."""
    with pytest.raises(SystemExit) as exc_info:
        main(["init", "--help"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "--backend" in captured.out


def test_verify_help_exits_0(capsys: pytest.CaptureFixture[str]) -> None:
    """`mcp-tools-sql verify --help` exits 0 and mentions verify."""
    with pytest.raises(SystemExit) as exc_info:
        main(["verify", "--help"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "verify" in captured.out


def test_version_flag_prints_version_and_exits_0(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`mcp-tools-sql --version` prints version and exits 0."""
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert re.search(rf"mcp-tools-sql {re.escape(__version__)}", output)


def test_help_subcommand_equivalent_to_help_flag(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`mcp-tools-sql help` prints the same usage as `--help`."""
    rc_sub = main(["help"])
    captured_sub = capsys.readouterr()

    rc_flag = main(["--help"])
    captured_flag = capsys.readouterr()

    assert rc_sub == 0
    assert rc_flag == 0
    assert captured_sub.out == captured_flag.out


def test_unknown_arg_emits_help_hint_and_exits_2(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Unknown flag exits 2 and prints the help hint to stderr."""
    with pytest.raises(SystemExit) as exc_info:
        main(["--bogus"])
    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert "Try 'mcp-tools-sql --help' for more information." in captured.err
