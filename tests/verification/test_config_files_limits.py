"""Tests for `verify_config_files` reporting invalid timeouts and limits."""

from __future__ import annotations

from pathlib import Path

from mcp_tools_sql.verification import verify_config_files


def _write(path: Path, text: str) -> Path:
    """Write ``text`` to ``path`` and return the path."""
    path.write_text(text, encoding="utf-8")
    return path


def _db_config(tmp_path: Path, extra: str = "") -> Path:
    """Write a sqlite database config, with optional extra connection keys."""
    sqlite_db = tmp_path / "real.sqlite"
    sqlite_db.write_bytes(b"")
    return _write(
        tmp_path / "db-config.toml",
        f'[connections.default]\nbackend = "sqlite"\n'
        f'path = "{sqlite_db.as_posix()}"\n{extra}',
    )


def test_limits_zero_reported_in_query_config_parse(tmp_path: Path) -> None:
    """``[limits] max_output_chars = 0`` fails the ``query_config_parse`` row."""
    query_cfg = _write(
        tmp_path / "mcp-tools-sql.toml",
        'connection = "default"\n\n[limits]\nmax_output_chars = 0\n',
    )

    result = verify_config_files(query_cfg, _db_config(tmp_path), tmp_path)

    assert result.checks["query_config_parse"]["ok"] is False
    assert "max_output_chars" in result.checks["query_config_parse"]["error"]


def test_hard_limit_above_max_count_rows_reported(tmp_path: Path) -> None:
    """A query exceeding ``max_count_rows`` fails ``query_config_parse``."""
    query_cfg = _write(
        tmp_path / "mcp-tools-sql.toml",
        'connection = "default"\n\n[limits]\nmax_count_rows = 200\n\n'
        '[queries.big]\nsql = "SELECT 1"\nmax_rows_hard = 500\n',
    )

    result = verify_config_files(query_cfg, _db_config(tmp_path), tmp_path)

    row = result.checks["query_config_parse"]
    assert row["ok"] is False
    assert row["error"] == (
        "[queries.big] max_rows_hard 500 exceeds [limits] max_count_rows 200"
    )
    # The other checks still run on the loaded entries.
    assert result.query_config is not None
    assert "big" in result.query_config.queries


def test_query_timeout_zero_reported_in_database_config_parse(
    tmp_path: Path,
) -> None:
    """``query_timeout_seconds = 0`` fails the ``database_config_parse`` row."""
    query_cfg = _write(tmp_path / "mcp-tools-sql.toml", 'connection = "default"\n')

    result = verify_config_files(
        query_cfg, _db_config(tmp_path, "query_timeout_seconds = 0\n"), tmp_path
    )

    assert result.checks["database_config_parse"]["ok"] is False
    assert "query_timeout_seconds" in result.checks["database_config_parse"]["error"]
