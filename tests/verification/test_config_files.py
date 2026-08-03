"""Tests for `verify_config_files`."""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_tools_sql.verification import verify_config_files


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


def test_verify_config_files_missing_returns_err(tmp_path: Path) -> None:
    """A non-existent --config path produces ok=False with the path in the error."""
    missing = tmp_path / "nope.toml"
    result = verify_config_files(missing, db_config_path=None)

    assert result["query_config_path"]["ok"] is False
    assert str(missing) in result["query_config_path"]["error"]
    assert result["overall_ok"] is False


def test_verify_config_files_valid_returns_ok(
    valid_query_config: Path,
    valid_database_config: Path,
) -> None:
    """Valid query + database config files both report ok=True."""
    result = verify_config_files(
        valid_query_config,
        db_config_path=valid_database_config,
    )

    assert result["query_config_path"]["ok"] is True
    assert result["query_config_parse"]["ok"] is True
    assert result["database_config_path"]["ok"] is True
    assert result["database_config_parse"]["ok"] is True
    assert result["overall_ok"] is True


# ---------------------------------------------------------------------------
# Cross-file static checks (rules 1/4/5/6)
# ---------------------------------------------------------------------------


def test_cross_file_single_target_legacy_passes(
    valid_query_config: Path,
    valid_database_config: Path,
) -> None:
    """Single-target legacy config emits a passing rule-1 row, no behaviour change."""
    result = verify_config_files(
        valid_query_config,
        db_config_path=valid_database_config,
    )

    assert result["connection_valid"]["ok"] is True
    assert result["connection_valid"]["value"] == "default"
    assert result["overall_ok"] is True


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

    result = verify_config_files(query_cfg, db_config_path=db_cfg)

    assert result["connection_valid"]["ok"] is True
    assert result["queries.q1.connection"]["ok"] is True
    assert result["queries.q1.database"]["ok"] is True
    assert result["queries.q2.database"]["ok"] is True
    assert result["updates.u1.connection"]["ok"] is True
    assert result["updates.u1.database"]["ok"] is True
    assert result["overall_ok"] is True


def test_cross_file_rule1_unknown_file_connection(tmp_path: Path) -> None:
    """An unknown file `connection` marks rule 1 as [ERR] (section no longer vanishes)."""
    query_cfg = tmp_path / "mcp-tools-sql.toml"
    query_cfg.write_text('connection = "ghost"\n', encoding="utf-8")
    db_cfg = tmp_path / "db-config.toml"
    db_cfg.write_text(
        '[connections.default]\nbackend = "sqlite"\npath = "/tmp/x.sqlite"\n',
        encoding="utf-8",
    )

    result = verify_config_files(query_cfg, db_config_path=db_cfg)

    assert result["connection_valid"]["ok"] is False
    assert result["overall_ok"] is False


def test_cross_file_rule4_unknown_per_query_connection(tmp_path: Path) -> None:
    """A per-query `connection` that is not configured marks rule 4 as [ERR]."""
    query_cfg = tmp_path / "mcp-tools-sql.toml"
    query_cfg.write_text(
        'connection = "main"\n'
        "\n"
        "[queries.x]\n"
        'sql = "SELECT 1"\n'
        'connection = "ghost"\n',
        encoding="utf-8",
    )
    db_cfg = tmp_path / "db-config.toml"
    db_cfg.write_text(
        "[connections.main]\n" 'backend = "mssql"\n' 'databases = ["sales"]\n',
        encoding="utf-8",
    )

    result = verify_config_files(query_cfg, db_config_path=db_cfg)

    assert result["queries.x.connection"]["ok"] is False
    assert result["overall_ok"] is False


def test_cross_file_rule5_per_query_database_not_member(tmp_path: Path) -> None:
    """A per-query `database` outside the connection's catalog marks rule 5 as [ERR]."""
    query_cfg = tmp_path / "mcp-tools-sql.toml"
    query_cfg.write_text(
        'connection = "main"\n'
        "\n"
        "[queries.x]\n"
        'sql = "SELECT 1"\n'
        'database = "finance"\n',
        encoding="utf-8",
    )
    db_cfg = tmp_path / "db-config.toml"
    db_cfg.write_text(
        "[connections.main]\n" 'backend = "mssql"\n' 'databases = ["sales", "hr"]\n',
        encoding="utf-8",
    )

    result = verify_config_files(query_cfg, db_config_path=db_cfg)

    assert result["queries.x.database"]["ok"] is False
    assert result["overall_ok"] is False


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

    result = verify_config_files(query_cfg, db_config_path=db_cfg)

    # The violation surfaces through the existing parse-error row ...
    assert result["database_config_parse"]["ok"] is False
    # ... and no bespoke rule-2/3/7 row nor any cross-file row is emitted,
    # because there is no loaded config object to inspect.
    assert "connection_valid" not in result
    assert result["overall_ok"] is False
