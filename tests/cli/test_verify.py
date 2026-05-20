"""Tests for the `verify` CLI subcommand."""

from __future__ import annotations

import argparse
import re
import shutil
import sqlite3
from pathlib import Path

import pytest

from mcp_tools_sql.cli.commands import verify as verify_cmd


def _make_args(
    *,
    config: Path | None,
    database_config: Path | None,
) -> argparse.Namespace:
    """Return a Namespace mirroring the parsed top-level CLI args needed by verify."""
    return argparse.Namespace(config=config, database_config=database_config)


@pytest.fixture
def valid_query_config(tmp_path: Path) -> Path:
    """Write a minimal valid query config file and return its path."""
    path = tmp_path / "mcp-tools-sql.toml"
    path.write_text('connection = "default"\n', encoding="utf-8")
    return path


@pytest.fixture
def valid_database_config(tmp_path: Path) -> Path:
    """Write a valid database config pointing at a real sqlite db in tmp_path."""
    sqlite_db = tmp_path / "real.sqlite"
    sqlite_db.write_bytes(b"")
    path = tmp_path / "db-config.toml"
    path.write_text(
        "[connections.default]\n"
        'backend = "sqlite"\n'
        f'path = "{sqlite_db.as_posix()}"\n',
        encoding="utf-8",
    )
    return path


# ---------------------------------------------------------------------------
# Orchestrator: run() output and exit code
# ---------------------------------------------------------------------------


def test_verify_run_prints_environment_and_config_sections(
    valid_query_config: Path,
    valid_database_config: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Stdout contains both `=== ENVIRONMENT ===` and `=== CONFIG ===`."""
    args = _make_args(
        config=valid_query_config,
        database_config=valid_database_config,
    )
    verify_cmd.run(args)
    captured = capsys.readouterr()

    assert "=== ENVIRONMENT ===" in captured.out
    assert "=== CONFIG ===" in captured.out


def test_verify_summary_line_format(
    valid_query_config: Path,
    valid_database_config: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Stdout contains a `N checks passed, M warnings, K errors` summary line."""
    args = _make_args(
        config=valid_query_config,
        database_config=valid_database_config,
    )
    verify_cmd.run(args)
    captured = capsys.readouterr()

    assert re.search(
        r"\d+ checks passed, \d+ warnings, \d+ errors",
        captured.out,
    )


def test_verify_exit_code_0_when_all_ok(
    valid_query_config: Path,
    valid_database_config: Path,
) -> None:
    """`run(args)` returns 0 when all checks pass."""
    args = _make_args(
        config=valid_query_config,
        database_config=valid_database_config,
    )
    assert verify_cmd.run(args) == 0


def test_verify_exit_code_1_when_config_missing(
    tmp_path: Path,
) -> None:
    """`run(args)` returns 1 when the query config path cannot be resolved."""
    args = _make_args(
        config=tmp_path / "missing.toml",
        database_config=tmp_path / "missing-db.toml",
    )
    assert verify_cmd.run(args) == 1


# ---------------------------------------------------------------------------
# Orchestrator: run() with the new sections
# ---------------------------------------------------------------------------


def test_verify_run_includes_dependencies_and_builtin_sections(
    valid_query_config: Path,
    valid_database_config: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Stdout contains both `=== DEPENDENCIES ===` and `=== BUILTIN ===`."""
    args = _make_args(
        config=valid_query_config,
        database_config=valid_database_config,
    )
    verify_cmd.run(args)
    captured = capsys.readouterr()

    assert "=== DEPENDENCIES ===" in captured.out
    assert "=== BUILTIN ===" in captured.out


def test_verify_run_uses_unknown_backend_when_config_invalid(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Invalid config → DEPENDENCIES rendered with backend=unknown ERR row."""
    args = _make_args(
        config=tmp_path / "missing.toml",
        database_config=tmp_path / "missing-db.toml",
    )
    verify_cmd.run(args)
    captured = capsys.readouterr()

    assert "=== DEPENDENCIES ===" in captured.out
    assert "cannot determine backend without valid config" in captured.out
    # verify_builtin still runs
    assert "=== BUILTIN ===" in captured.out


def test_verify_sqlite_full_run_all_ok(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Issue test (viii): valid SQLite config → all rows OK in env/config/deps/builtin.

    Connection section is added in step 7; for now this asserts no `[ERR]`
    rows and that the sqlite \"no optional dependencies\" line is present.
    """
    sqlite_db = tmp_path / "real.sqlite"
    sqlite_db.write_bytes(b"")  # touch a file (CONFIG section only checks parse)

    query_cfg = tmp_path / "mcp-tools-sql.toml"
    query_cfg.write_text('connection = "default"\n', encoding="utf-8")

    db_cfg = tmp_path / "db-config.toml"
    db_cfg.write_text(
        "[connections.default]\n"
        'backend = "sqlite"\n'
        f'path = "{sqlite_db.as_posix()}"\n',
        encoding="utf-8",
    )

    args = _make_args(config=query_cfg, database_config=db_cfg)
    verify_cmd.run(args)
    captured = capsys.readouterr()

    assert "[ERR]" not in captured.out
    assert "no optional dependencies for sqlite" in captured.out


def test_verify_detects_missing_connection(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Issue test (ix): query config refers to a name not in db config.

    The mismatch surfaces via backend resolution failing, so DEPENDENCIES
    renders as the `unknown` backend ERR row. The CONNECTION section is
    omitted because the connection cannot be resolved at all. Exit code 1.
    """
    query_cfg = tmp_path / "mcp-tools-sql.toml"
    query_cfg.write_text('connection = "missing_name"\n', encoding="utf-8")

    db_cfg = tmp_path / "db-config.toml"
    db_cfg.write_text(
        '[connections.default]\nbackend = "sqlite"\npath = "/tmp/x.sqlite"\n',
        encoding="utf-8",
    )

    args = _make_args(config=query_cfg, database_config=db_cfg)
    rc = verify_cmd.run(args)
    captured = capsys.readouterr()

    assert "cannot determine backend without valid config" in captured.out
    assert rc == 1


# ---------------------------------------------------------------------------
# Orchestrator: run() with M1 complete (CONNECTION + INSTALL + skip-M2)
# ---------------------------------------------------------------------------


def test_verify_run_skips_m2_on_connection_failure(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Issue test (xi): connection fails → skip-M2 summary appears in stdout."""
    query_cfg = tmp_path / "mcp-tools-sql.toml"
    query_cfg.write_text('connection = "default"\n', encoding="utf-8")

    db_cfg = tmp_path / "db-config.toml"
    db_cfg.write_text(
        '[connections.default]\nbackend = "sqlite"\npath = ""\n',
        encoding="utf-8",
    )

    args = _make_args(config=query_cfg, database_config=db_cfg)
    rc = verify_cmd.run(args)
    captured = capsys.readouterr()

    assert "connection failed; skipped 0 query checks, 0 update checks" in captured.out
    assert rc == 1


def test_verify_warn_for_sensitive_keys_in_query_config(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Query config with `password = ...` → [WARN] row in output, no extra ERR."""
    sqlite_db = tmp_path / "real.sqlite"
    sqlite_db.write_bytes(b"")

    query_cfg = tmp_path / "mcp-tools-sql.toml"
    query_cfg.write_text(
        'connection = "default"\npassword = "leaked"\n',
        encoding="utf-8",
    )

    db_cfg = tmp_path / "db-config.toml"
    db_cfg.write_text(
        "[connections.default]\n"
        'backend = "sqlite"\n'
        f'path = "{sqlite_db.as_posix()}"\n',
        encoding="utf-8",
    )

    args = _make_args(config=query_cfg, database_config=db_cfg)
    rc = verify_cmd.run(args)
    captured = capsys.readouterr()

    assert "[WARN]" in captured.out
    assert "query_config_sensitive_keys" in captured.out
    # Warn alone does not flip the exit code to 1.
    assert rc == 0


def test_verify_full_sqlite_run_returns_0(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Issue tests (vii)+(viii): valid sqlite config + connectable db → exit 0."""
    sqlite_db = tmp_path / "real.sqlite"
    sqlite_db.write_bytes(b"")

    query_cfg = tmp_path / "mcp-tools-sql.toml"
    query_cfg.write_text('connection = "default"\n', encoding="utf-8")

    db_cfg = tmp_path / "db-config.toml"
    db_cfg.write_text(
        "[connections.default]\n"
        'backend = "sqlite"\n'
        f'path = "{sqlite_db.as_posix()}"\n',
        encoding="utf-8",
    )

    args = _make_args(config=query_cfg, database_config=db_cfg)
    rc = verify_cmd.run(args)
    captured = capsys.readouterr()

    assert rc == 0
    assert "=== CONNECTION ===" in captured.out
    assert "[ERR]" not in captured.out


def test_verify_full_run_returns_1_on_error(tmp_path: Path) -> None:
    """Issue test (vii): missing query config → exit 1."""
    args = _make_args(
        config=tmp_path / "missing.toml",
        database_config=tmp_path / "missing-db.toml",
    )
    assert verify_cmd.run(args) == 1


def test_verify_full_run_with_queries_and_updates_returns_0(
    sqlite_db: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Issue tests (vii)+(viii)+(x): full sqlite happy path → exit 0."""
    query_cfg = tmp_path / "mcp-tools-sql.toml"
    query_cfg.write_text(
        'connection = "default"\n'
        "\n"
        "[queries.list_customers]\n"
        'sql = "SELECT * FROM customers WHERE country = :country"\n'
        "max_rows_default = 10\n"
        "\n"
        "[queries.list_customers.params.country]\n"
        'name = "country"\n'
        'type = "str"\n'
        "\n"
        "[updates.set_customer_name]\n"
        'table = "customers"\n'
        "\n"
        "[updates.set_customer_name.key]\n"
        'field = "id"\n'
        'type = "int"\n'
        "\n"
        "[[updates.set_customer_name.fields]]\n"
        'field = "name"\n'
        'type = "str"\n'
        "\n"
        "[[updates.set_customer_name.fields]]\n"
        'field = "country"\n'
        'type = "str"\n',
        encoding="utf-8",
    )

    db_cfg = tmp_path / "db-config.toml"
    db_cfg.write_text(
        "[connections.default]\n"
        'backend = "sqlite"\n'
        f'path = "{sqlite_db.as_posix()}"\n',
        encoding="utf-8",
    )

    args = _make_args(config=query_cfg, database_config=db_cfg)
    rc = verify_cmd.run(args)
    captured = capsys.readouterr()

    assert rc == 0
    assert "=== QUERIES ===" in captured.out
    assert "=== UPDATES ===" in captured.out
    assert "[ERR]" not in captured.out


# ---------------------------------------------------------------------------
# CLI snapshot regression test for QUERIES + UPDATES sections
# ---------------------------------------------------------------------------


def _extract_section(text: str, title: str) -> str:
    """Return the body of `=== TITLE ===` up to the next blank line."""
    lines = text.split("\n")
    in_section = False
    body: list[str] = []
    for line in lines:
        if line == f"=== {title} ===":
            in_section = True
            continue
        if in_section:
            if line == "":
                break
            body.append(line)
    return "\n".join(body)


def _prepare_snapshot_db(db_path: Path) -> None:
    """Create the fixed sqlite schema used by the verify snapshot test."""
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("CREATE TABLE users (id INTEGER, email TEXT)")
        conn.execute("CREATE TABLE customers (id INTEGER, name TEXT, country TEXT)")
        conn.commit()
    finally:
        conn.close()


def test_verify_cli_queries_updates_snapshot(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """CLI stdout for QUERIES + UPDATES is byte-identical to the committed snapshot."""
    sqlite_db = tmp_path / "snapshot.sqlite"
    _prepare_snapshot_db(sqlite_db)

    fixtures_dir = Path(__file__).parent / "fixtures"
    query_cfg = tmp_path / "mcp-tools-sql.toml"
    shutil.copyfile(fixtures_dir / "verify_snapshot.toml", query_cfg)

    db_cfg = tmp_path / "db-config.toml"
    db_cfg.write_text(
        "[connections.default]\n"
        'backend = "sqlite"\n'
        f'path = "{sqlite_db.as_posix()}"\n',
        encoding="utf-8",
    )

    args = _make_args(config=query_cfg, database_config=db_cfg)
    verify_cmd.run(args)
    captured = capsys.readouterr().out

    queries_block = _extract_section(captured, "QUERIES")
    updates_block = _extract_section(captured, "UPDATES")
    actual = f"=== QUERIES ===\n{queries_block}\n=== UPDATES ===\n{updates_block}\n"
    expected = (fixtures_dir / "verify_snapshot.txt").read_text(encoding="utf-8")
    assert actual == expected
