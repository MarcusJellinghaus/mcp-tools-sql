"""Tests for the verification orchestrator."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from mcp_tools_sql.verification.orchestrator import (
    collect_install_instructions,
    verify_all,
)


def _stub_ok_backend() -> MagicMock:
    """Return a stub backend whose ``SELECT 1`` probe succeeds."""
    backend = MagicMock(name="stub_backend")
    backend.connect.return_value = None
    backend.execute_query.return_value = [{"v": 1}]
    backend.close.return_value = None
    return backend


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


# ---------------------------------------------------------------------------
# CONNECTION: per-pair probing
# ---------------------------------------------------------------------------


def test_verify_all_connection_single_pair_is_prefixed(
    valid_sqlite_configs: tuple[Path, Path],
) -> None:
    """Single-target config → one CONNECTION row-group labelled by the pair."""
    query_cfg, db_cfg = valid_sqlite_configs

    sections, _ = verify_all(query_cfg, db_cfg)

    connection_section = dict(sections)["CONNECTION"]
    keys = [k for k in connection_section if k != "overall_ok"]
    assert keys, "expected at least one CONNECTION row"
    assert all(k.startswith("default/main.") for k in keys)
    assert connection_section["default/main.select_1"]["ok"] is True


def test_verify_all_connection_probes_every_pair(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two databases on one connection → both pairs probed, both select_1 rows."""
    monkeypatch.setattr(
        "mcp_tools_sql.backends.registry.create_backend",
        MagicMock(return_value=_stub_ok_backend()),
    )
    monkeypatch.setattr(
        "mcp_tools_sql.verification.connection.socket.gethostbyname",
        MagicMock(return_value="10.0.0.1"),
    )

    query_cfg = tmp_path / "mcp-tools-sql.toml"
    query_cfg.write_text('connection = "prod"\n', encoding="utf-8")

    db_cfg = tmp_path / "db-config.toml"
    db_cfg.write_text(
        "[connections.prod]\n"
        'backend = "mssql"\n'
        'host = "h"\n'
        'databases = ["sales", "hr"]\n'
        'password = "pw"\n',
        encoding="utf-8",
    )

    sections, _ = verify_all(query_cfg, db_cfg)

    connection_section = dict(sections)["CONNECTION"]
    assert "prod/sales.select_1" in connection_section
    assert "prod/hr.select_1" in connection_section
    assert connection_section["prod/sales.select_1"]["ok"] is True
    assert connection_section["prod/hr.select_1"]["ok"] is True


def test_verify_all_connection_overall_ok_false_when_a_pair_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failing pair flips the merged CONNECTION ``overall_ok`` to False."""
    failing = MagicMock(name="failing_backend")
    failing.connect.return_value = None
    failing.execute_query.side_effect = RuntimeError("cannot connect")
    failing.close.return_value = None
    monkeypatch.setattr(
        "mcp_tools_sql.backends.registry.create_backend",
        MagicMock(return_value=failing),
    )
    monkeypatch.setattr(
        "mcp_tools_sql.verification.connection.socket.gethostbyname",
        MagicMock(return_value="10.0.0.1"),
    )

    query_cfg = tmp_path / "mcp-tools-sql.toml"
    query_cfg.write_text('connection = "prod"\n', encoding="utf-8")

    db_cfg = tmp_path / "db-config.toml"
    db_cfg.write_text(
        "[connections.prod]\n"
        'backend = "mssql"\n'
        'host = "h"\n'
        'databases = ["sales", "hr"]\n'
        'password = "pw"\n',
        encoding="utf-8",
    )

    sections, skip_summary = verify_all(query_cfg, db_cfg)

    connection_section = dict(sections)["CONNECTION"]
    assert connection_section["prod/sales.select_1"]["ok"] is False
    assert connection_section["prod/hr.select_1"]["ok"] is False
    assert connection_section["overall_ok"] is False
    # Default pair failed → M2 skipped.
    assert skip_summary is not None


def test_verify_all_skips_query_pinned_to_unreachable_connection(
    tmp_path: Path,
    sqlite_db: Path,
) -> None:
    """Reachable default + a query pinned to a down connection → per-target skip.

    The default connection is reachable, so M2 runs; a query pinned to the
    unreachable ``prod`` connection is reported as a skip row naming ``prod``
    while an unpinned query in the same run still gets a real verdict.
    """
    query_cfg = tmp_path / "mcp-tools-sql.toml"
    query_cfg.write_text(
        'connection = "default"\n'
        "\n"
        "[queries.local]\n"
        'sql = "SELECT * FROM customers"\n'
        "max_rows_default = 10\n"
        "\n"
        "[queries.remote]\n"
        'sql = "SELECT * FROM customers"\n'
        "max_rows_default = 10\n"
        'connection = "prod"\n',
        encoding="utf-8",
    )

    db_cfg = tmp_path / "db-config.toml"
    db_cfg.write_text(
        "[connections.default]\n"
        'backend = "sqlite"\n'
        f'path = "{sqlite_db.as_posix()}"\n'
        "\n"
        "[connections.prod]\n"
        'backend = "sqlite"\n'
        'path = ""\n',
        encoding="utf-8",
    )

    sections, skip_summary = verify_all(query_cfg, db_cfg)

    queries_section = dict(sections)["QUERIES"]
    # Unpinned query resolves to the reachable default → real verdict.
    assert queries_section["local.sql"]["ok"] is True
    assert queries_section["local.sql"]["value"] == "EXPLAIN ok"
    # Pinned-to-down query is skipped, naming the connection.
    assert queries_section["remote.sql"].get("warn") is True
    assert "prod" in queries_section["remote.sql"]["value"]
    # Default reachable → M2 ran, not skipped wholesale.
    assert skip_summary is None
