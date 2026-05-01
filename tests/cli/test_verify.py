"""Tests for the `verify` CLI subcommand (skeleton + first two sections)."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

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
    """Write a minimal valid database config file and return its path."""
    path = tmp_path / "db-config.toml"
    path.write_text(
        '[connections.default]\nbackend = "sqlite"\npath = "/tmp/db.sqlite"\n',
        encoding="utf-8",
    )
    return path


# ---------------------------------------------------------------------------
# verify_environment
# ---------------------------------------------------------------------------


def test_verify_environment_returns_python_version() -> None:
    """`python_version` entry is OK and matches the running interpreter."""
    result = verify_cmd.verify_environment()

    assert result["python_version"]["ok"] is True
    expected = (
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    )
    assert result["python_version"]["value"] == expected


def test_verify_environment_overall_ok_true_when_packages_present() -> None:
    """`mcp_tools_sql` and `mcp_coder_utils` resolve in the test environment."""
    result = verify_cmd.verify_environment()

    assert result["mcp_tools_sql"]["ok"] is True
    assert result["mcp_coder_utils"]["ok"] is True
    assert result["overall_ok"] is True


# ---------------------------------------------------------------------------
# verify_config_files
# ---------------------------------------------------------------------------


def test_verify_config_files_missing_returns_err(tmp_path: Path) -> None:
    """A non-existent --config path produces ok=False with the path in the error."""
    missing = tmp_path / "nope.toml"
    result = verify_cmd.verify_config_files(missing, db_config_path=None)

    assert result["query_config_path"]["ok"] is False
    assert str(missing) in result["query_config_path"]["error"]
    assert result["overall_ok"] is False


def test_verify_config_files_valid_returns_ok(
    valid_query_config: Path,
    valid_database_config: Path,
) -> None:
    """Valid query + database config files both report ok=True."""
    result = verify_cmd.verify_config_files(
        valid_query_config,
        db_config_path=valid_database_config,
    )

    assert result["query_config_path"]["ok"] is True
    assert result["query_config_parse"]["ok"] is True
    assert result["database_config_path"]["ok"] is True
    assert result["database_config_parse"]["ok"] is True
    assert result["overall_ok"] is True


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
# verify_dependencies
# ---------------------------------------------------------------------------


def test_verify_dependencies_sqlite_shows_info_line() -> None:
    """sqlite backend returns a single OK info entry."""
    result = verify_cmd.verify_dependencies("sqlite")

    assert result["info"]["ok"] is True
    assert "no optional dependencies" in result["info"]["value"]
    assert result["overall_ok"] is True


def test_verify_dependencies_unknown_backend_returns_err() -> None:
    """`unknown` backend returns ok=False with a clear error message."""
    result = verify_cmd.verify_dependencies("unknown")

    assert result["overall_ok"] is False
    assert result["backend"]["ok"] is False
    assert "cannot determine backend" in result["backend"]["error"]


def test_verify_dependencies_postgresql_when_psycopg_missing() -> None:
    """postgresql branch reports ok=False with install_hint when psycopg missing."""
    with patch.dict(sys.modules, {"psycopg": None}):
        result = verify_cmd.verify_dependencies("postgresql")

    assert result["psycopg"]["ok"] is False
    assert "(not installed)" in result["psycopg"]["value"]
    assert "pip install" in result["psycopg"]["install_hint"]
    assert result["overall_ok"] is False


def test_verify_dependencies_mssql_when_pyodbc_missing() -> None:
    """mssql branch reports ok=False for pyodbc when missing, and skips driver."""
    with patch.dict(sys.modules, {"pyodbc": None}):
        result = verify_cmd.verify_dependencies("mssql")

    assert result["pyodbc"]["ok"] is False
    assert "pip install mcp-tools-sql[mssql]" in result["pyodbc"]["install_hint"]
    assert result["odbc_driver"]["ok"] is False
    assert result["overall_ok"] is False


def test_verify_dependencies_mssql_with_pyodbc_and_driver() -> None:
    """mssql branch returns ok when pyodbc present and a SQL Server driver exists."""
    fake_pyodbc = MagicMock()
    fake_pyodbc.version = "5.0.1"
    fake_pyodbc.drivers = MagicMock(
        return_value=["ODBC Driver 18 for SQL Server", "Other Driver"]
    )
    with patch.dict(sys.modules, {"pyodbc": fake_pyodbc}):
        result = verify_cmd.verify_dependencies("mssql")

    assert result["pyodbc"]["ok"] is True
    assert result["odbc_driver"]["ok"] is True
    assert "SQL Server" in result["odbc_driver"]["value"]
    assert result["overall_ok"] is True


def test_verify_dependencies_mssql_with_pyodbc_no_driver() -> None:
    """mssql branch returns ok=False for driver when no SQL Server driver found."""
    fake_pyodbc = MagicMock()
    fake_pyodbc.version = "5.0.1"
    fake_pyodbc.drivers = MagicMock(return_value=["SQLite ODBC Driver"])
    with patch.dict(sys.modules, {"pyodbc": fake_pyodbc}):
        result = verify_cmd.verify_dependencies("mssql")

    assert result["pyodbc"]["ok"] is True
    assert result["odbc_driver"]["ok"] is False
    assert "ODBC Driver 18 for SQL Server" in result["odbc_driver"]["install_hint"]
    assert result["overall_ok"] is False


# ---------------------------------------------------------------------------
# verify_builtin
# ---------------------------------------------------------------------------


def test_verify_builtin_returns_query_count() -> None:
    """`default_queries_loaded` and `tools_registered_count` report >0 entries."""
    result = verify_cmd.verify_builtin()

    assert result["default_queries_loaded"]["ok"] is True
    match = re.match(r"(\d+) queries", result["default_queries_loaded"]["value"])
    assert match is not None
    assert int(match.group(1)) > 0
    assert result["tools_registered_count"]["ok"] is True
    assert result["overall_ok"] is True


def test_verify_reports_default_queries_count() -> None:
    """Issue test (x): BUILTIN section shows ``{N} queries`` text."""
    result = verify_cmd.verify_builtin()

    assert "queries" in result["default_queries_loaded"]["value"]


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

    In step 6 the mismatch surfaces via backend resolution failing, so
    DEPENDENCIES renders as the `unknown` backend ERR row. Step 7 will
    add a dedicated CONNECTION section that improves this signal.
    """
    query_cfg = tmp_path / "mcp-tools-sql.toml"
    query_cfg.write_text('connection = "missing_name"\n', encoding="utf-8")

    db_cfg = tmp_path / "db-config.toml"
    db_cfg.write_text(
        '[connections.default]\nbackend = "sqlite"\npath = "/tmp/x.sqlite"\n',
        encoding="utf-8",
    )

    args = _make_args(config=query_cfg, database_config=db_cfg)
    verify_cmd.run(args)
    captured = capsys.readouterr()

    assert "cannot determine backend without valid config" in captured.out
