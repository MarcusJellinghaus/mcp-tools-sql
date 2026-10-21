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
    conn.execute("INSERT INTO customers VALUES (1, 'Bank A')")
    conn.execute("INSERT INTO customers VALUES (2, 'Bank B')")
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


def _write_query_bad_table_config(
    tmp_path: Path, *, allow_updates: bool = False
) -> None:
    """Write configs where `queries.foo` references a non-existent table."""
    db = tmp_path / "test.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO customers VALUES (1, 'Bob')")
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
        "[queries.bad_table]\n"
        'description = "Bad table query"\n'
        'sql = "SELECT * FROM no_such_table"\n'
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


def test_builtin_read_tables_against_seeded_db_exits_0(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`tool read_tables` against a seeded sqlite db exits 0 and lists the table."""
    _write_configs(tmp_path)

    rc = main(_argv(tmp_path, "read_tables", "--schema", "main"))
    out = capsys.readouterr().out

    assert rc == 0
    assert "customers" in out


def _write_query_with_id_param_config(tmp_path: Path) -> None:
    """Write a sqlite config with a `[queries.by_id]` entry bound on `:id`."""
    db = tmp_path / "test.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO customers VALUES (1, 'Alice')")
    conn.commit()
    conn.close()

    qcfg = tmp_path / "mcp-tools-sql.toml"
    qcfg.write_text(
        'connection = "default"\n'
        "\n"
        "[queries.by_id]\n"
        'description = "Customer by id"\n'
        'sql = "SELECT * FROM customers WHERE id = :id"\n'
        "\n"
        "[queries.by_id.params.id]\n"
        'name = "id"\n'
        'type = "int"\n'
    )
    dbcfg = tmp_path / "db.toml"
    dbcfg.write_text(
        f'[connections.default]\nbackend = "sqlite"\npath = "{db.as_posix()}"\n'
        "\n[security]\nallow_updates = false\n"
    )


def test_configured_query_with_flag_exits_0_and_contains_row(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`tool query_by_id --id 1` exits 0 and prints the matching customer row."""
    _write_query_with_id_param_config(tmp_path)

    rc = main(_argv(tmp_path, "query_by_id", "--id", "1"))
    out = capsys.readouterr().out

    assert rc == 0
    assert "Alice" in out


def test_query_with_invalid_max_rows_exits_3_no_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`tool query_foo --max_rows -5` violates the `Field(ge=...)` floor: exit 3."""
    _write_configs(tmp_path)

    rc = main(_argv(tmp_path, "query_foo", "--max_rows", "-5"))
    captured = capsys.readouterr()

    assert rc == 3
    assert "Traceback" not in captured.err


def test_query_against_missing_table_exits_1_no_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A query referencing a non-existent table: exit 1 on sqlite.

    SQLite raises `sqlite3.OperationalError` for both connection failures and
    "no such table" — the documented, accepted sqlite-only exit-1 limitation
    (see `tool_dispatch.py`'s `_CONNECTION_EXC`).
    """
    _write_query_bad_table_config(tmp_path)

    rc = main(_argv(tmp_path, "query_bad_table"))
    captured = capsys.readouterr()

    assert rc == 1
    assert "Traceback" not in captured.err


def test_update_omitted_optional_field_leaves_column_unchanged(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`update_set_name` sets the field when given, leaves it untouched when omitted."""
    _write_query_bad_table_config(tmp_path, allow_updates=True)

    rc = main(_argv(tmp_path, "update_set_name", "--id", "1", "--name", "Alice"))
    capsys.readouterr()
    assert rc == 0

    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    name = conn.execute("SELECT name FROM customers WHERE id = 1").fetchone()[0]
    conn.close()
    assert name == "Alice"

    main(_argv(tmp_path, "update_set_name", "--id", "1"))
    captured2 = capsys.readouterr()
    assert "Traceback" not in captured2.err

    conn = sqlite3.connect(str(db_path))
    name_after = conn.execute("SELECT name FROM customers WHERE id = 1").fetchone()[0]
    conn.close()
    assert name_after == "Alice"


def test_validate_sql_simple_select_exits_0_with_valid_text(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`tool validate_sql --sql ... --param id=5` exits 0 and prints `Valid.`."""
    _write_configs(tmp_path)

    rc = main(
        _argv(
            tmp_path,
            "validate_sql",
            "--sql",
            "SELECT 1 WHERE :id = :id",
            "--param",
            "id=5",
        )
    )
    out = capsys.readouterr().out

    assert rc == 0
    assert out.strip() == "Valid."


def test_summarize_columns_with_repeated_column_flag_exits_0(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`tool summarize_columns --schema main --table customers --column id --column name`."""
    _write_configs(tmp_path)

    rc = main(
        _argv(
            tmp_path,
            "summarize_columns",
            "--schema",
            "main",
            "--table",
            "customers",
            "--column",
            "id",
            "--column",
            "name",
        )
    )
    out = capsys.readouterr().out

    assert rc == 0
    assert "id" in out
    assert "name" in out


def test_connection_failure_on_db_touching_tool_exits_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A sqlite path whose parent directory doesn't exist: `read_tables` exits 1."""
    _write_configs(tmp_path)

    bad_db = tmp_path / "missing_dir" / "test.db"
    dbcfg = tmp_path / "db.toml"
    dbcfg.write_text(
        f'[connections.default]\nbackend = "sqlite"\npath = "{bad_db.as_posix()}"\n'
        "\n[security]\nallow_updates = false\n"
    )

    rc = main(_argv(tmp_path, "read_tables", "--schema", "main"))
    captured = capsys.readouterr()

    assert rc == 1
    assert "Traceback" not in captured.err
