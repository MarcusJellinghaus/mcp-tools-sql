"""Tests for the verification orchestrator."""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_tools_sql.verification.orchestrator import (
    collect_install_instructions,
    verify_all,
)

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
    result = collect_install_instructions(sections)

    hints = [entry["value"] for key, entry in result.items() if key != "overall_ok"]
    assert hints == ["pip install mcp-tools-sql[mssql]", "pip install other"]
    assert result["overall_ok"] is True


# ---------------------------------------------------------------------------
# verify_all
# ---------------------------------------------------------------------------


@pytest.fixture
def valid_sqlite_configs(tmp_path: Path, sqlite_db: Path) -> tuple[Path, Path]:
    """Return ``(query_cfg, db_cfg)`` pointing at the seeded sqlite db."""
    query_cfg = tmp_path / "mcp-tools-sql.toml"
    query_cfg.write_text('connection = "default"\n', encoding="utf-8")

    db_cfg = tmp_path / "db-config.toml"
    db_cfg.write_text(
        "[connections.default]\n"
        'backend = "sqlite"\n'
        f'path = "{sqlite_db.as_posix()}"\n',
        encoding="utf-8",
    )
    return query_cfg, db_cfg


def test_verify_all_returns_tuple_of_sections_and_skip_summary(
    valid_sqlite_configs: tuple[Path, Path],
) -> None:
    """``verify_all`` returns ``(sections_list, skip_summary)``."""
    query_cfg, db_cfg = valid_sqlite_configs

    result = verify_all(query_cfg, db_cfg)

    assert isinstance(result, tuple)
    assert len(result) == 2
    sections, skip_summary = result
    assert isinstance(sections, list)
    assert skip_summary is None or isinstance(skip_summary, str)


def test_verify_all_section_order_on_happy_path(
    valid_sqlite_configs: tuple[Path, Path],
) -> None:
    """Sections appear in the canonical order on the happy path."""
    query_cfg, db_cfg = valid_sqlite_configs

    sections, skip_summary = verify_all(query_cfg, db_cfg)

    titles = [title for title, _ in sections]
    # Canonical order: ENVIRONMENT, CONFIG, DEPENDENCIES, BUILTIN, then
    # CONNECTION + QUERIES + UPDATES, optionally INSTALL INSTRUCTIONS last.
    assert titles[:4] == ["ENVIRONMENT", "CONFIG", "DEPENDENCIES", "BUILTIN"]
    assert "CONNECTION" in titles
    # Happy path: no skip summary
    assert skip_summary is None


def test_verify_all_skip_summary_on_connection_failure(
    tmp_path: Path,
) -> None:
    """When connection fails, ``skip_summary`` is a non-empty string."""
    query_cfg = tmp_path / "mcp-tools-sql.toml"
    query_cfg.write_text('connection = "default"\n', encoding="utf-8")

    db_cfg = tmp_path / "db-config.toml"
    db_cfg.write_text(
        '[connections.default]\nbackend = "sqlite"\npath = ""\n',
        encoding="utf-8",
    )

    sections, skip_summary = verify_all(query_cfg, db_cfg)

    titles = [title for title, _ in sections]
    assert "CONNECTION" in titles
    # No QUERIES / UPDATES because connection failed.
    assert "QUERIES" not in titles
    assert "UPDATES" not in titles
    assert skip_summary is not None
    assert "connection failed" in skip_summary


def test_verify_all_omits_install_instructions_when_empty(
    valid_sqlite_configs: tuple[Path, Path],
) -> None:
    """The INSTALL INSTRUCTIONS section is only appended when non-empty."""
    query_cfg, db_cfg = valid_sqlite_configs

    sections, _ = verify_all(query_cfg, db_cfg)

    titles = [title for title, _ in sections]
    # Happy sqlite path → no install hints → no INSTALL INSTRUCTIONS section.
    assert "INSTALL INSTRUCTIONS" not in titles
