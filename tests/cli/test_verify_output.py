"""Tests for `verify` output modes and the public verification API."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import mcp_tools_sql.verification as verification
from mcp_tools_sql.main import main
from mcp_tools_sql.verification import verify_all


@pytest.fixture
def query_config(tmp_path: Path) -> Path:
    """Write a minimal valid query config file and return its path."""
    path = tmp_path / "mcp-tools-sql.toml"
    path.write_text('connection = "default"\n', encoding="utf-8")
    return path


@pytest.fixture
def database_config(tmp_path: Path) -> Path:
    """Write a valid database config pointing at a real sqlite db in tmp_path."""
    sqlite_db = tmp_path / "real.sqlite"
    sqlite_db.write_bytes(b"")
    path = tmp_path / "db-config.toml"
    path.write_text(
        f'[connections.default]\nbackend = "sqlite"\npath = "{sqlite_db.as_posix()}"\n',
        encoding="utf-8",
    )
    return path


def _argv(query: Path, database: Path, *verify_args: str) -> list[str]:
    """Return the CLI argv for `verify` with the given configs and flags."""
    return [
        "--config",
        str(query),
        "--database-config",
        str(database),
        "--console-only",
        "verify",
        *verify_args,
    ]


def test_json_output_is_the_verify_all_result(
    query_config: Path,
    database_config: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`verify --output-format json` prints exactly the `verify_all` result."""
    rc = main(_argv(query_config, database_config, "--output-format", "json"))
    document = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert set(document) == {
        "sections",
        "skipped_queries",
        "skipped_updates",
        "summary",
    }
    expected = json.loads(json.dumps(verify_all(query_config, database_config)))
    assert document == expected


def test_json_output_missing_config_exits_1_with_valid_json(
    tmp_path: Path,
    database_config: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A missing query config still yields valid JSON, with exit code 1."""
    rc = main(
        _argv(tmp_path / "missing.toml", database_config, "--output-format", "json")
    )
    document = json.loads(capsys.readouterr().out)

    assert rc == 1
    assert "sections" in document


def test_unknown_output_format_exits_2(
    query_config: Path,
    database_config: Path,
) -> None:
    """`verify --output-format xml` is rejected by argparse with exit code 2."""
    with pytest.raises(SystemExit) as exc_info:
        main(_argv(query_config, database_config, "--output-format", "xml"))
    assert exc_info.value.code == 2


def test_public_api_exports() -> None:
    """The stable public names are exported from `mcp_tools_sql.verification`."""
    for name in (
        "verify_all",
        "CheckResult",
        "VerifySection",
        "VerifySummary",
        "VerifyResult",
    ):
        assert name in verification.__all__
