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
