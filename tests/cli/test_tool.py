"""Tests for the `tool` CLI subcommand (discovery surface only)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from mcp_tools_sql.main import main


def _write_configs(tmp_path: Path, *, allow_updates: bool = False) -> None:
    """Write a sqlite `mcp-tools-sql.toml` + `db.toml` pair under tmp_path."""
    db = tmp_path / "test.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT)")
    conn.commit()
    conn.close()

    qcfg = tmp_path / "mcp-tools-sql.toml"
    qcfg.write_text(
        'connection = "default"\n'
        "\n"
        "[queries.foo]\n"
        'description = "Foo query"\n'
        'sql = "SELECT * FROM customers"\n'
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


def _argv(tmp_path: Path, *extra: str) -> list[str]:
    """Build `mcp-tools-sql --config ... --database-config ... tool <extra>`."""
    return [
        "--config",
        str(tmp_path / "mcp-tools-sql.toml"),
        "--database-config",
        str(tmp_path / "db.toml"),
        "tool",
        *extra,
    ]


def test_bare_tool_and_help_both_print_overview(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Bare `tool` and `tool --help` print the same overview and return 0."""
    _write_configs(tmp_path)

    rc_bare = main(_argv(tmp_path))
    out_bare = capsys.readouterr().out

    rc_help = main(_argv(tmp_path, "--help"))
    out_help = capsys.readouterr().out

    assert rc_bare == 0
    assert rc_help == 0
    assert out_bare == out_help
    assert "Exit codes:" in out_bare
    assert "read_tables" in out_bare


def test_overview_includes_builtin_and_query_excludes_update_when_disallowed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Overview lists a builtin and `query_foo`; `update_*` absent when disallowed."""
    _write_configs(tmp_path, allow_updates=False)

    rc = main(_argv(tmp_path))
    out = capsys.readouterr().out

    assert rc == 0
    assert "read_tables" in out
    assert "query_foo" in out
    assert "update_set_name" not in out


def test_overview_includes_update_when_allowed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`update_set_name` appears in the overview when `allow_updates = true`."""
    _write_configs(tmp_path, allow_updates=True)

    rc = main(_argv(tmp_path))
    out = capsys.readouterr().out

    assert rc == 0
    assert "update_set_name" in out


def test_tool_detail_help_prints_docstring_and_every_param(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`tool query_foo --help` prints the full docstring and parameter names."""
    _write_configs(tmp_path)

    rc = main(_argv(tmp_path, "query_foo", "--help"))
    out = capsys.readouterr().out

    assert rc == 0
    assert "Foo query" in out
    assert "max_rows" in out


def test_unknown_tool_name_exits_2_with_usage_hint_no_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`tool bogus_name` exits 2 with a usage hint on stderr, no traceback."""
    _write_configs(tmp_path)

    with pytest.raises(SystemExit) as exc_info:
        main(_argv(tmp_path, "bogus_name"))
    captured = capsys.readouterr()

    assert exc_info.value.code == 2
    assert "Try '" in captured.err
    assert "Traceback" not in captured.err


def test_missing_config_prints_clean_error_and_exits_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A nonexistent --config path makes bare `tool` exit 1 with no traceback."""
    argv = ["--config", str(tmp_path / "missing.toml"), "tool"]

    rc = main(argv)
    captured = capsys.readouterr()

    assert rc == 1
    assert "Error:" in captured.err
    assert "Traceback" not in captured.err
