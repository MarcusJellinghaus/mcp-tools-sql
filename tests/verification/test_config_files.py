"""Tests for `verify_config_files`."""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_tools_sql.verification import verify_config_files
from mcp_tools_sql.verification._helpers import checks_ok


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
        f'[connections.default]\nbackend = "sqlite"\npath = "{sqlite_db.as_posix()}"\n',
        encoding="utf-8",
    )
    return path


def _write_query_config(tmp_path: Path, text: str) -> Path:
    """Write ``text`` as the project query config and return its path."""
    path = tmp_path / "mcp-tools-sql.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_verify_config_files_missing_returns_err(tmp_path: Path) -> None:
    """A non-existent --config path produces ok=False with the path in the error."""
    missing = tmp_path / "nope.toml"
    result = verify_config_files(missing, db_config_path=None, project_dir=tmp_path)

    assert result.checks["query_config_path"]["ok"] is False
    assert str(missing) in result.checks["query_config_path"]["error"]
    assert checks_ok(result.checks) is False
    assert result.query_config is None


def test_verify_config_files_valid_returns_ok(
    valid_query_config: Path,
    valid_database_config: Path,
    tmp_path: Path,
) -> None:
    """Valid query + database config files both report ok=True."""
    result = verify_config_files(
        valid_query_config,
        db_config_path=valid_database_config,
        project_dir=tmp_path,
    )

    assert result.checks["query_config_path"]["ok"] is True
    assert result.checks["query_config_parse"]["ok"] is True
    assert result.checks["database_config_path"]["ok"] is True
    assert result.checks["database_config_parse"]["ok"] is True
    assert checks_ok(result.checks) is True
    assert result.query_config is not None
    assert result.db_config is not None


# ---------------------------------------------------------------------------
# Per-entry loading
# ---------------------------------------------------------------------------


def test_invalid_query_entry_gets_own_row(
    tmp_path: Path,
    valid_database_config: Path,
) -> None:
    """One bad ``[queries.*]`` entry gets its own ERR row; the good one loads."""
    query_cfg = _write_query_config(
        tmp_path,
        'connection = "default"\n\n'
        '[queries.good]\nsql = "SELECT 1"\n\n'
        '[queries.bad]\ndescription = "no sql"\n',
    )

    result = verify_config_files(query_cfg, valid_database_config, tmp_path)

    assert result.checks["query_config_parse"]["ok"] is True
    assert result.checks["queries.bad.parse"]["ok"] is False
    assert result.checks["queries.bad.parse"]["severity"] == "error"
    assert "queries.good.parse" not in result.checks
    assert result.query_config is not None
    assert list(result.query_config.queries) == ["good"]


def test_invalid_update_entry_gets_own_row(
    tmp_path: Path,
    valid_database_config: Path,
) -> None:
    """A bad ``[updates.*]`` entry gets its own row; valid queries stay loaded."""
    query_cfg = _write_query_config(
        tmp_path,
        'connection = "default"\n\n'
        '[queries.good]\nsql = "SELECT 1"\n\n'
        '[updates.bad]\ntable = "t"\nfields = "x"\n',
    )

    result = verify_config_files(query_cfg, valid_database_config, tmp_path)

    assert result.checks["updates.bad.parse"]["ok"] is False
    assert result.query_config is not None
    assert list(result.query_config.queries) == ["good"]
    assert result.query_config.updates == {}


def test_non_table_queries_gets_kind_row(
    tmp_path: Path,
    valid_database_config: Path,
) -> None:
    """``queries = 5`` yields a ``queries.parse`` row and zero queries."""
    query_cfg = _write_query_config(tmp_path, 'connection = "default"\nqueries = 5\n')

    result = verify_config_files(query_cfg, valid_database_config, tmp_path)

    assert result.checks["query_config_parse"]["ok"] is True
    assert result.checks["queries.parse"]["ok"] is False
    assert result.query_config is not None
    assert result.query_config.queries == {}


def test_top_level_failure_skips_entry_rows(
    tmp_path: Path,
    valid_database_config: Path,
) -> None:
    """A top-level validation error emits no per-entry rows and no query config."""
    query_cfg = _write_query_config(
        tmp_path,
        "connection = 5\n\n"
        '[queries.bad]\ndescription = "no sql"\n\n'
        '[updates.bad]\nfields = "x"\n',
    )

    result = verify_config_files(query_cfg, valid_database_config, tmp_path)

    assert result.checks["query_config_parse"]["ok"] is False
    for key in ("queries.parse", "queries.bad.parse", "updates.parse"):
        assert key not in result.checks
    assert "updates.bad.parse" not in result.checks
    assert result.query_config is None


def test_row_order_with_entry_rows(
    tmp_path: Path,
    valid_database_config: Path,
) -> None:
    """Entry rows sit between ``query_config_parse`` and the database rows."""
    query_cfg = _write_query_config(
        tmp_path,
        'connection = "default"\npassword = "x"\n\n'
        '[queries.bad]\ndescription = "no sql"\n\n'
        '[updates.bad]\nfields = "x"\n',
    )

    result = verify_config_files(query_cfg, valid_database_config, tmp_path)

    assert list(result.checks)[:7] == [
        "query_config_path",
        "query_config_parse",
        "queries.bad.parse",
        "updates.bad.parse",
        "query_config_sensitive_keys",
        "database_config_path",
        "database_config_parse",
    ]


# ---------------------------------------------------------------------------
# allow_updates
# ---------------------------------------------------------------------------


def test_allow_updates_false_from_database_config(
    valid_query_config: Path,
    tmp_path: Path,
) -> None:
    """``[security] allow_updates = false`` is reported as False."""
    db_cfg = tmp_path / "db-config.toml"
    db_cfg.write_text(
        '[connections.default]\nbackend = "sqlite"\npath = "x.sqlite"\n\n'
        "[security]\nallow_updates = false\n",
        encoding="utf-8",
    )

    result = verify_config_files(valid_query_config, db_cfg, tmp_path)

    assert result.allow_updates is False


def test_allow_updates_none_when_database_config_invalid(
    valid_query_config: Path,
    tmp_path: Path,
) -> None:
    """A database config parse error gives ``allow_updates is None``."""
    db_cfg = tmp_path / "db-config.toml"
    db_cfg.write_text('[connections.default]\nport = "nope"\n', encoding="utf-8")

    result = verify_config_files(valid_query_config, db_cfg, tmp_path)

    assert result.checks["database_config_parse"]["ok"] is False
    assert result.db_config is None
    assert result.allow_updates is None


def test_allow_updates_default_when_database_config_absent(
    valid_query_config: Path,
    tmp_path: Path,
) -> None:
    """An absent database config falls back to the default (True)."""
    result = verify_config_files(
        valid_query_config, tmp_path / "missing.toml", tmp_path
    )

    assert result.db_config is None
    assert result.allow_updates is True


# ---------------------------------------------------------------------------
# project_dir
# ---------------------------------------------------------------------------


def test_project_dir_drives_discovery(
    tmp_path: Path,
    valid_database_config: Path,
) -> None:
    """With no ``config_path``, the query config is discovered under project_dir."""
    proj = tmp_path / "proj"
    proj.mkdir()
    expected = proj / "mcp-tools-sql.toml"
    expected.write_text('connection = "default"\n', encoding="utf-8")

    result = verify_config_files(None, valid_database_config, project_dir=proj)

    assert result.checks["query_config_path"]["ok"] is True
    assert result.checks["query_config_path"]["value"] == str(expected)


# ---------------------------------------------------------------------------
# Cross-file static checks (rules 1/4/5/6)
# ---------------------------------------------------------------------------


def test_cross_file_single_target_legacy_passes(
    valid_query_config: Path,
    valid_database_config: Path,
    tmp_path: Path,
) -> None:
    """Single-target legacy config emits a passing rule-1 row, no behaviour change."""
    result = verify_config_files(
        valid_query_config,
        db_config_path=valid_database_config,
        project_dir=tmp_path,
    )

    assert result.checks["connection_valid"]["ok"] is True
    assert result.checks["connection_valid"]["value"] == "default"
    assert checks_ok(result.checks) is True


def test_cross_file_valid_multi_config_all_pass(tmp_path: Path) -> None:
    """A valid multi-connection config makes every cross-file row PASS."""
    query_cfg = tmp_path / "mcp-tools-sql.toml"
    query_cfg.write_text(
        'connection = "main"\n'
        "\n"
        "[queries.q1]\n"
        'sql = "SELECT 1"\n'
        'connection = "reporting"\n'
        'database = "analytics"\n'
        "\n"
        "[queries.q2]\n"
        'sql = "SELECT 2"\n'
        'database = "hr"\n'
        "\n"
        "[updates.u1]\n"
        'table = "people"\n'
        'connection = "main"\n'
        'database = "sales"\n',
        encoding="utf-8",
    )
    db_cfg = tmp_path / "db-config.toml"
    db_cfg.write_text(
        "[connections.main]\n"
        'backend = "mssql"\n'
        'host = "localhost"\n'
        'databases = ["sales", "hr"]\n'
        'default_database = "sales"\n'
        "\n"
        "[connections.reporting]\n"
        'backend = "postgresql"\n'
        'host = "localhost"\n'
        'databases = ["analytics"]\n',
        encoding="utf-8",
    )

    result = verify_config_files(query_cfg, db_config_path=db_cfg, project_dir=tmp_path)

    assert result.checks["connection_valid"]["ok"] is True
    assert result.checks["queries.q1.connection"]["ok"] is True
    assert result.checks["queries.q1.database"]["ok"] is True
    assert result.checks["queries.q2.database"]["ok"] is True
    assert result.checks["updates.u1.connection"]["ok"] is True
    assert result.checks["updates.u1.database"]["ok"] is True
    assert checks_ok(result.checks) is True


def test_cross_file_rule1_unknown_file_connection(tmp_path: Path) -> None:
    """An unknown file `connection` marks rule 1 as [ERR] (section no longer vanishes)."""
    query_cfg = tmp_path / "mcp-tools-sql.toml"
    query_cfg.write_text('connection = "ghost"\n', encoding="utf-8")
    db_cfg = tmp_path / "db-config.toml"
    db_cfg.write_text(
        '[connections.default]\nbackend = "sqlite"\npath = "/tmp/x.sqlite"\n',
        encoding="utf-8",
    )

    result = verify_config_files(query_cfg, db_config_path=db_cfg, project_dir=tmp_path)

    assert result.checks["connection_valid"]["ok"] is False
    assert checks_ok(result.checks) is False


def test_cross_file_rule4_unknown_per_query_connection(tmp_path: Path) -> None:
    """A per-query `connection` that is not configured marks rule 4 as [ERR]."""
    query_cfg = tmp_path / "mcp-tools-sql.toml"
    query_cfg.write_text(
        'connection = "main"\n\n[queries.x]\nsql = "SELECT 1"\nconnection = "ghost"\n',
        encoding="utf-8",
    )
    db_cfg = tmp_path / "db-config.toml"
    db_cfg.write_text(
        '[connections.main]\nbackend = "mssql"\ndatabases = ["sales"]\n',
        encoding="utf-8",
    )

    result = verify_config_files(query_cfg, db_config_path=db_cfg, project_dir=tmp_path)

    assert result.checks["queries.x.connection"]["ok"] is False
    assert checks_ok(result.checks) is False


def test_cross_file_skips_invalid_entries(
    tmp_path: Path,
    valid_database_config: Path,
) -> None:
    """Cross-file rows walk valid entries only."""
    query_cfg = _write_query_config(
        tmp_path,
        'connection = "default"\n\n[queries.bad]\nconnection = "ghost"\n',
    )

    result = verify_config_files(query_cfg, valid_database_config, tmp_path)

    assert "queries.bad.parse" in result.checks
    assert "queries.bad.connection" not in result.checks
    assert result.checks["connection_valid"]["ok"] is True


def test_cross_file_rule5_per_query_database_not_member(tmp_path: Path) -> None:
    """A per-query `database` outside the connection's catalog marks rule 5 as [ERR]."""
    query_cfg = tmp_path / "mcp-tools-sql.toml"
    query_cfg.write_text(
        'connection = "main"\n\n[queries.x]\nsql = "SELECT 1"\ndatabase = "finance"\n',
        encoding="utf-8",
    )
    db_cfg = tmp_path / "db-config.toml"
    db_cfg.write_text(
        '[connections.main]\nbackend = "mssql"\ndatabases = ["sales", "hr"]\n',
        encoding="utf-8",
    )

    result = verify_config_files(query_cfg, db_config_path=db_cfg, project_dir=tmp_path)

    assert result.checks["queries.x.database"]["ok"] is False
    assert checks_ok(result.checks) is False


def test_cross_file_rule237_violation_surfaces_via_parse_row(tmp_path: Path) -> None:
    """A default_database violation is caught at load, not re-emitted as a bespoke row."""
    query_cfg = tmp_path / "mcp-tools-sql.toml"
    query_cfg.write_text('connection = "main"\n', encoding="utf-8")
    db_cfg = tmp_path / "db-config.toml"
    db_cfg.write_text(
        "[connections.main]\n"
        'backend = "mssql"\n'
        'databases = ["sales"]\n'
        'default_database = "hr"\n',
        encoding="utf-8",
    )

    result = verify_config_files(query_cfg, db_config_path=db_cfg, project_dir=tmp_path)

    # The violation surfaces through the existing parse-error row ...
    assert result.checks["database_config_parse"]["ok"] is False
    # ... and no bespoke rule-2/3/7 row nor any cross-file row is emitted,
    # because there is no loaded config object to inspect.
    assert "connection_valid" not in result.checks
    assert checks_ok(result.checks) is False


def test_sensitive_keys_row_is_warning(
    tmp_path: Path,
    valid_database_config: Path,
) -> None:
    """Sensitive keys in the query config yield a warning row that keeps CONFIG ok."""
    query_cfg = tmp_path / "mcp-tools-sql.toml"
    query_cfg.write_text(
        'connection = "default"\npassword = "leaked"\n', encoding="utf-8"
    )

    result = verify_config_files(
        query_cfg, db_config_path=valid_database_config, project_dir=tmp_path
    )

    row = result.checks["query_config_sensitive_keys"]
    assert row["ok"] is False
    assert row["severity"] == "warning"
    assert "password" in row["value"]
    assert checks_ok(result.checks) is True


def test_database_config_parse_error_hides_password(
    valid_query_config: Path,
    tmp_path: Path,
) -> None:
    """A database config parse error does not echo the connection's password."""
    db_cfg = tmp_path / "db-config.toml"
    db_cfg.write_text(
        "[connections.c]\n"
        'backend = "mssql"\n'
        'host = "h"\n'
        'database = "a"\n'
        'databases = ["b"]\n'
        'password = "s3cret-pw"\n',
        encoding="utf-8",
    )

    result = verify_config_files(
        valid_query_config, db_config_path=db_cfg, project_dir=tmp_path
    )

    row = result.checks["database_config_parse"]
    assert row["ok"] is False
    assert "s3cret-pw" not in row.get("error", "")
