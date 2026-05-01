"""Tests for the `verify` CLI subcommand (skeleton + first two sections)."""

from __future__ import annotations

import argparse
import re
import sys
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
