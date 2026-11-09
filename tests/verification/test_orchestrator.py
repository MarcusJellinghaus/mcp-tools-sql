"""Tests for the verification orchestrator."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from mcp_tools_sql.verification._helpers import (
    VerifyResult,
    VerifySection,
    make_entry,
)
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


def _by_title(result: VerifyResult) -> dict[str, VerifySection]:
    """Index the result's sections by title."""
    return {section["title"]: section for section in result["sections"]}


def _titles(result: VerifyResult) -> list[str]:
    """Return the section titles in order."""
    return [section["title"] for section in result["sections"]]


# ---------------------------------------------------------------------------
# collect_install_instructions
# ---------------------------------------------------------------------------


def test_collect_install_instructions_aggregates_unique() -> None:
    """Failed entries with identical hints dedupe; ok entries' hints are ignored."""
    sections: list[VerifySection] = [
        {
            "title": "DEPENDENCIES",
            "ok": False,
            "checks": {
                "pyodbc": make_entry(
                    ok=False,
                    value="(not installed)",
                    error="no module",
                    install_hint="pip install mcp-tools-sql[mssql]",
                ),
                "psycopg": make_entry(
                    ok=False,
                    value="(not installed)",
                    error="no module",
                    install_hint="pip install mcp-tools-sql[mssql]",
                ),
                "ok_one": make_entry(
                    ok=True,
                    value="x",
                    install_hint="pip install ignored-because-ok",
                ),
            },
        },
        {
            "title": "OTHER",
            "ok": False,
            "checks": {
                "blah": make_entry(
                    ok=False,
                    value="x",
                    error="fail",
                    install_hint="pip install other",
                ),
                "warned": make_entry(
                    ok=False,
                    value="x",
                    install_hint="pip install ignored-because-warning",
                    severity="warning",
                ),
            },
        },
    ]
    result = collect_install_instructions(sections)

    hints = [entry["value"] for entry in result.values()]
    assert hints == ["pip install mcp-tools-sql[mssql]", "pip install other"]
    assert list(result) == ["hint_0", "hint_1"]
    assert all(entry["ok"] for entry in result.values())


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
        f'[connections.default]\nbackend = "sqlite"\npath = "{sqlite_db.as_posix()}"\n',
        encoding="utf-8",
    )
    return query_cfg, db_cfg


def test_verify_all_returns_verify_result_shape(
    valid_sqlite_configs: tuple[Path, Path],
) -> None:
    """``verify_all`` returns the ``VerifyResult`` dict with well-formed sections."""
    query_cfg, db_cfg = valid_sqlite_configs

    result = verify_all(query_cfg, db_cfg)

    assert set(result) == {"sections", "skipped_queries", "skipped_updates"}
    assert isinstance(result["sections"], list)
    for section in result["sections"]:
        assert set(section) == {"title", "ok", "checks"}
        assert isinstance(section["ok"], bool)
        assert "overall_ok" not in section["checks"]


def test_verify_all_section_order_on_happy_path(
    valid_sqlite_configs: tuple[Path, Path],
) -> None:
    """Sections appear in the canonical order on the happy path."""
    query_cfg, db_cfg = valid_sqlite_configs

    result = verify_all(query_cfg, db_cfg)

    titles = _titles(result)
    # Canonical order: ENVIRONMENT, CONFIG, DEPENDENCIES, BUILTIN, then
    # CONNECTION + QUERIES + UPDATES, optionally INSTALL INSTRUCTIONS last.
    assert titles[:4] == ["ENVIRONMENT", "CONFIG", "DEPENDENCIES", "BUILTIN"]
    assert "CONNECTION" in titles
    # Happy path: nothing skipped.
    assert result["skipped_queries"] is None
    assert result["skipped_updates"] is None


def test_verify_all_skip_counts_on_connection_failure(
    tmp_path: Path,
) -> None:
    """When the connection fails, the skip counts are ints."""
    query_cfg = tmp_path / "mcp-tools-sql.toml"
    query_cfg.write_text('connection = "default"\n', encoding="utf-8")

    db_cfg = tmp_path / "db-config.toml"
    db_cfg.write_text(
        '[connections.default]\nbackend = "sqlite"\npath = ""\n',
        encoding="utf-8",
    )

    result = verify_all(query_cfg, db_cfg)

    titles = _titles(result)
    assert "CONNECTION" in titles
    # No QUERIES / UPDATES because connection failed.
    assert "QUERIES" not in titles
    assert "UPDATES" not in titles
    assert result["skipped_queries"] == 0
    assert result["skipped_updates"] == 0


def test_verify_all_unresolved_targets_has_no_connection_section(
    tmp_path: Path,
) -> None:
    """An unknown file connection → no CONNECTION section and no skip counts."""
    query_cfg = tmp_path / "mcp-tools-sql.toml"
    query_cfg.write_text('connection = "missing_name"\n', encoding="utf-8")

    db_cfg = tmp_path / "db-config.toml"
    db_cfg.write_text(
        '[connections.default]\nbackend = "sqlite"\npath = "/tmp/x.sqlite"\n',
        encoding="utf-8",
    )

    result = verify_all(query_cfg, db_cfg)

    assert "CONNECTION" not in _titles(result)
    assert result["skipped_queries"] is None
    assert result["skipped_updates"] is None


def test_verify_all_memory_sqlite_counts_as_reachable(tmp_path: Path) -> None:
    """A ':memory:' warning does not make the target unreachable."""
    query_cfg = tmp_path / "mcp-tools-sql.toml"
    query_cfg.write_text(
        'connection = "default"\n\n[queries.one]\nsql = "SELECT 1"\n'
        "max_rows_default = 10\n",
        encoding="utf-8",
    )

    db_cfg = tmp_path / "db-config.toml"
    db_cfg.write_text(
        '[connections.default]\nbackend = "sqlite"\npath = ":memory:"\n',
        encoding="utf-8",
    )

    result = verify_all(query_cfg, db_cfg)

    sections = _by_title(result)
    connection = sections["CONNECTION"]
    assert connection["checks"]["default/main.path"]["severity"] == "warning"
    assert connection["ok"] is True
    assert "QUERIES" in sections
    assert result["skipped_queries"] is None


def test_verify_all_omits_install_instructions_when_empty(
    valid_sqlite_configs: tuple[Path, Path],
) -> None:
    """The INSTALL INSTRUCTIONS section is only appended when non-empty."""
    query_cfg, db_cfg = valid_sqlite_configs

    result = verify_all(query_cfg, db_cfg)

    # Happy sqlite path → no install hints → no INSTALL INSTRUCTIONS section.
    assert "INSTALL INSTRUCTIONS" not in _titles(result)


# ---------------------------------------------------------------------------
# CONNECTION: per-pair probing
# ---------------------------------------------------------------------------


def test_verify_all_connection_single_pair_is_prefixed(
    valid_sqlite_configs: tuple[Path, Path],
) -> None:
    """Single-target config → one CONNECTION row-group labelled by the pair."""
    query_cfg, db_cfg = valid_sqlite_configs

    result = verify_all(query_cfg, db_cfg)

    checks = _by_title(result)["CONNECTION"]["checks"]
    keys = list(checks)
    assert keys, "expected at least one CONNECTION row"
    assert all(k.startswith("default/main.") for k in keys)
    assert checks["default/main.select_1"]["ok"] is True


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

    result = verify_all(query_cfg, db_cfg)

    checks = _by_title(result)["CONNECTION"]["checks"]
    assert "prod/sales.select_1" in checks
    assert "prod/hr.select_1" in checks
    assert checks["prod/sales.select_1"]["ok"] is True
    assert checks["prod/hr.select_1"]["ok"] is True


def test_verify_all_connection_not_ok_when_a_pair_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failing pair makes the merged CONNECTION section ``ok`` False."""
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

    result = verify_all(query_cfg, db_cfg)

    connection = _by_title(result)["CONNECTION"]
    assert connection["checks"]["prod/sales.select_1"]["ok"] is False
    assert connection["checks"]["prod/hr.select_1"]["ok"] is False
    assert connection["ok"] is False
    # Default pair failed → M2 skipped.
    assert result["skipped_queries"] is not None


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

    result = verify_all(query_cfg, db_cfg)

    checks = _by_title(result)["QUERIES"]["checks"]
    # Unpinned query resolves to the reachable default → real verdict.
    assert checks["local.sql"]["ok"] is True
    assert checks["local.sql"]["value"] == "EXPLAIN ok"
    # Pinned-to-down query is skipped, naming the connection.
    assert checks["remote.sql"]["ok"] is False
    assert checks["remote.sql"]["severity"] == "warning"
    assert "prod" in checks["remote.sql"]["value"]
    # Default reachable → M2 ran, not skipped wholesale.
    assert result["skipped_queries"] is None
