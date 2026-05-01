"""Tests for the `verify` CLI subcommand."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mcp_tools_sql.backends.base import DatabaseBackend
from mcp_tools_sql.cli.commands import verify as verify_cmd
from mcp_tools_sql.config.models import ConnectionConfig


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
# verify_connection
# ---------------------------------------------------------------------------


def _sqlite_connection(path: Path) -> ConnectionConfig:
    """Build a ConnectionConfig pointing at the given sqlite file."""
    return ConnectionConfig(backend="sqlite", path=str(path))


def test_verify_connection_sqlite_select_1_ok(tmp_path: Path) -> None:
    """Real sqlite tmp file → all rows ok=True, select_1 value 'ok'."""
    db_path = tmp_path / "real.sqlite"
    db_path.write_bytes(b"")
    result, open_backend = verify_cmd.verify_connection(_sqlite_connection(db_path))
    try:
        assert result["backend"]["ok"] is True
        assert result["path"]["ok"] is True
        assert result["select_1"]["ok"] is True
        assert result["select_1"]["value"] == "ok"
        assert result["overall_ok"] is True
    finally:
        if open_backend is not None:
            open_backend.close()


def test_verify_connection_sqlite_missing_path() -> None:
    """Empty path → ok=False with helpful error and select_1 fails."""
    conn = ConnectionConfig(backend="sqlite", path="")
    result, open_backend = verify_cmd.verify_connection(conn)
    try:
        assert result["path"]["ok"] is False
        assert "must be set" in result["path"]["error"]
        assert result["select_1"]["ok"] is False
        assert result["overall_ok"] is False
    finally:
        if open_backend is not None:
            open_backend.close()


def test_verify_connection_unimplemented_backend_is_err() -> None:
    """`postgresql` (no impl) → select_1 fails via create_backend ValueError."""
    conn = ConnectionConfig(
        backend="postgresql",
        host="localhost",
        port=5432,
        database="db",
        password="pw",
    )
    result, open_backend = verify_cmd.verify_connection(conn)
    try:
        assert result["select_1"]["ok"] is False
        assert "Unsupported backend" in result["select_1"]["error"]
    finally:
        if open_backend is not None:
            open_backend.close()


def test_verify_connection_credential_env_var_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Env var unset → credentials row ok=False."""
    monkeypatch.delenv("MY_VERIFY_TEST_VAR", raising=False)
    conn = ConnectionConfig(
        backend="mssql",
        host="localhost",
        port=1433,
        database="db",
        credential_env_var="MY_VERIFY_TEST_VAR",
    )
    result, open_backend = verify_cmd.verify_connection(conn)
    try:
        assert result["credentials"]["ok"] is False
        assert "MY_VERIFY_TEST_VAR" in result["credentials"]["value"]
        assert "<missing>" in result["credentials"]["value"]
    finally:
        if open_backend is not None:
            open_backend.close()


def test_verify_connection_credential_env_var_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Env var set → credentials row ok=True."""
    monkeypatch.setenv("MY_VERIFY_TEST_VAR", "secret")
    conn = ConnectionConfig(
        backend="mssql",
        host="localhost",
        port=1433,
        database="db",
        credential_env_var="MY_VERIFY_TEST_VAR",
    )
    result, open_backend = verify_cmd.verify_connection(conn)
    try:
        assert result["credentials"]["ok"] is True
        assert "<set>" in result["credentials"]["value"]
    finally:
        if open_backend is not None:
            open_backend.close()


def test_verify_connection_returns_open_backend_on_success(tmp_path: Path) -> None:
    """On success the second element is a connected DatabaseBackend instance."""
    db_path = tmp_path / "real.sqlite"
    db_path.write_bytes(b"")
    result, open_backend = verify_cmd.verify_connection(_sqlite_connection(db_path))
    try:
        assert result["overall_ok"] is True
        assert open_backend is not None
        assert isinstance(open_backend, DatabaseBackend)
        # The backend is connected — a second SELECT should work without re-connect.
        rows = open_backend.execute_query("SELECT 1 AS one")
        assert rows == [{"one": 1}]
    finally:
        if open_backend is not None:
            open_backend.close()


def test_verify_connection_returns_none_backend_on_failure() -> None:
    """On select_1 failure the second tuple element is None."""
    conn = ConnectionConfig(backend="sqlite", path="")
    result, open_backend = verify_cmd.verify_connection(conn)
    assert result["select_1"]["ok"] is False
    assert open_backend is None


# ---------------------------------------------------------------------------
# collect_install_instructions
# ---------------------------------------------------------------------------


def test_collect_install_instructions_aggregates_unique() -> None:
    """Failed entries with identical hints dedupe; ok entries' hints are ignored."""
    sections: list[tuple[str, dict[str, object]]] = [
        (
            "DEPENDENCIES",
            {
                "pyodbc": {
                    "ok": False,
                    "value": "(not installed)",
                    "error": "no module",
                    "install_hint": "pip install mcp-tools-sql[mssql]",
                },
                "psycopg": {
                    "ok": False,
                    "value": "(not installed)",
                    "error": "no module",
                    "install_hint": "pip install mcp-tools-sql[mssql]",
                },
                "ok_one": {
                    "ok": True,
                    "value": "x",
                    "error": "",
                    "install_hint": "pip install ignored-because-ok",
                },
                "overall_ok": False,
            },
        ),
        (
            "OTHER",
            {
                "blah": {
                    "ok": False,
                    "value": "x",
                    "error": "fail",
                    "install_hint": "pip install other",
                },
                "overall_ok": False,
            },
        ),
    ]
    result = verify_cmd.collect_install_instructions(sections)

    hints = [entry["value"] for key, entry in result.items() if key != "overall_ok"]
    assert hints == ["pip install mcp-tools-sql[mssql]", "pip install other"]
    assert result["overall_ok"] is True


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
