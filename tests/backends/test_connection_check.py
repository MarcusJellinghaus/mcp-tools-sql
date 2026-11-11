"""Tests for the per-connection dependency check."""

from __future__ import annotations

import pytest

from mcp_tools_sql.backends import connection_check
from mcp_tools_sql.backends.connection_check import (
    MSSQL_INSTALL_HINT,
    ODBC_DRIVER_HINT,
    DependencyRow,
    check_connections,
)
from mcp_tools_sql.config.models import ConnectionConfig


def _missing_pyodbc() -> str:
    """Probe that raises like a missing pyodbc import."""
    raise ImportError("No module named 'pyodbc'")


def _patch_pyodbc(
    monkeypatch: pytest.MonkeyPatch, drivers: list[str], version: str = "5.1.0"
) -> list[int]:
    """Patch the pyodbc probes; return a one-item counter of drivers() calls."""
    calls = [0]

    def _drivers() -> list[str]:
        calls[0] += 1
        return list(drivers)

    monkeypatch.setattr(connection_check, "pyodbc_version", lambda: version)
    monkeypatch.setattr(connection_check, "odbc_drivers", _drivers)
    return calls


def _by_key(rows: list[DependencyRow]) -> dict[str, DependencyRow]:
    """Index rows by ``<connection>.<key>``."""
    return {f"{r.connection}.{r.key}": r for r in rows}


def test_sqlite_connection_yields_one_info_row() -> None:
    """A sqlite connection has no optional dependencies: one OK info row."""
    rows = check_connections({"default": ConnectionConfig(backend="sqlite")})

    assert len(rows) == 1
    assert rows[0].connection == "default"
    assert rows[0].key == "info"
    assert rows[0].ok is True
    assert "no optional dependencies for sqlite" in rows[0].value


def test_unsupported_backend_yields_backend_error() -> None:
    """An unsupported backend is an ERR row naming it and the supported set."""
    rows = check_connections(
        {"pg": ConnectionConfig(backend="postgresql", database="x")}
    )

    assert len(rows) == 1
    row = rows[0]
    assert (row.connection, row.key, row.ok) == ("pg", "backend", False)
    assert "unsupported backend 'postgresql'" in row.error
    for name in ("mssql", "pyodbc", "sqlite"):
        assert name in row.error


def test_mssql_without_pyodbc_reports_install_hint_and_skips_driver(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing pyodbc → pyodbc ERR with the [mssql] hint, odbc_driver skipped."""
    monkeypatch.setattr(connection_check, "pyodbc_version", _missing_pyodbc)

    rows = _by_key(
        check_connections({"prod": ConnectionConfig(backend="mssql", database="x")})
    )

    assert list(rows) == ["prod.pyodbc", "prod.odbc_driver"]
    assert rows["prod.pyodbc"].ok is False
    assert rows["prod.pyodbc"].value == "(not installed)"
    assert "pyodbc" in rows["prod.pyodbc"].error
    assert rows["prod.pyodbc"].hint == MSSQL_INSTALL_HINT
    assert "[mssql]" in rows["prod.pyodbc"].hint
    assert rows["prod.odbc_driver"].ok is False
    assert rows["prod.odbc_driver"].value == "(skipped)"
    assert rows["prod.odbc_driver"].error == "pyodbc not available"


def test_configured_driver_installed_is_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    """The configured driver present in drivers() → OK row with its name."""
    _patch_pyodbc(
        monkeypatch, ["ODBC Driver 17 for SQL Server", "ODBC Driver 18 for SQL Server"]
    )
    cfg = ConnectionConfig(
        backend="mssql", database="x", driver="ODBC Driver 18 for SQL Server"
    )

    rows = _by_key(check_connections({"prod": cfg}))

    assert rows["prod.pyodbc"].ok is True
    assert rows["prod.pyodbc"].value == "5.1.0"
    assert rows["prod.odbc_driver"].ok is True
    assert rows["prod.odbc_driver"].value == "ODBC Driver 18 for SQL Server"


def test_configured_driver_not_installed_names_it_and_lists_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A configured driver missing from drivers() → ERR naming both sides."""
    _patch_pyodbc(monkeypatch, ["ODBC Driver 18 for SQL Server", "SQLite ODBC Driver"])
    cfg = ConnectionConfig(
        backend="mssql", database="x", driver="ODBC Driver 17 for SQL Server"
    )

    row = _by_key(check_connections({"prod": cfg}))["prod.odbc_driver"]

    assert row.ok is False
    assert row.value == "(not found: 'ODBC Driver 17 for SQL Server')"
    assert "'ODBC Driver 17 for SQL Server'" in row.error
    assert "ODBC Driver 18 for SQL Server" in row.error
    assert "SQLite ODBC Driver" in row.error
    assert row.hint == ODBC_DRIVER_HINT


def test_configured_driver_not_installed_with_no_drivers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No drivers installed at all → the error says ``(none)``."""
    _patch_pyodbc(monkeypatch, [])
    cfg = ConnectionConfig(
        backend="mssql", database="x", driver="ODBC Driver 18 for SQL Server"
    )

    row = _by_key(check_connections({"prod": cfg}))["prod.odbc_driver"]

    assert row.ok is False
    assert "installed: (none)" in row.error


def test_empty_driver_falls_back_to_any_sql_server_driver(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``driver=""`` accepts the first driver containing ``SQL Server``."""
    _patch_pyodbc(monkeypatch, ["Other Driver", "ODBC Driver 18 for SQL Server"])

    row = _by_key(
        check_connections(
            {"prod": ConnectionConfig(backend="mssql", database="x", driver="")}
        )
    )["prod.odbc_driver"]

    assert row.ok is True
    assert row.value == "ODBC Driver 18 for SQL Server"


def test_empty_driver_without_sql_server_driver_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``driver=""`` and no ``SQL Server`` driver → ERR ``(none found)``."""
    _patch_pyodbc(monkeypatch, ["SQLite ODBC Driver"])

    row = _by_key(
        check_connections(
            {"prod": ConnectionConfig(backend="mssql", database="x", driver="")}
        )
    )["prod.odbc_driver"]

    assert row.ok is False
    assert row.value == "(none found)"
    assert row.hint == ODBC_DRIVER_HINT


def test_drivers_error_yields_error_row(monkeypatch: pytest.MonkeyPatch) -> None:
    """An exception from drivers() → odbc_driver ERR ``(error)``."""

    def _raise() -> list[str]:
        raise RuntimeError("odbc boom")

    monkeypatch.setattr(connection_check, "pyodbc_version", lambda: "5.1.0")
    monkeypatch.setattr(connection_check, "odbc_drivers", _raise)

    row = _by_key(
        check_connections({"prod": ConnectionConfig(backend="mssql", database="x")})
    )["prod.odbc_driver"]

    assert row.ok is False
    assert row.value == "(error)"
    assert row.error == "odbc boom"


def test_pyodbc_alias_gets_the_same_rows_as_mssql(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``backend = "pyodbc"`` is checked exactly like ``mssql``."""
    _patch_pyodbc(monkeypatch, ["ODBC Driver 18 for SQL Server"])

    alias = check_connections({"c": ConnectionConfig(backend="pyodbc", database="x")})
    canonical = check_connections(
        {"c": ConnectionConfig(backend="mssql", database="x")}
    )

    assert alias == canonical
    assert [r.key for r in alias] == ["pyodbc", "odbc_driver"]


def test_two_mssql_connections_probe_drivers_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """pyodbc is probed at most once per call, however many connections use it."""
    calls = _patch_pyodbc(monkeypatch, ["ODBC Driver 18 for SQL Server"])

    rows = check_connections(
        {
            "a": ConnectionConfig(backend="mssql", database="x"),
            "b": ConnectionConfig(backend="pyodbc", database="x"),
        }
    )

    assert calls[0] == 1
    assert [f"{r.connection}.{r.key}" for r in rows] == [
        "a.pyodbc",
        "a.odbc_driver",
        "b.pyodbc",
        "b.odbc_driver",
    ]


def test_rows_follow_connection_order(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rows are emitted in connection order, mixing backends."""
    _patch_pyodbc(monkeypatch, ["ODBC Driver 18 for SQL Server"])

    rows = check_connections(
        {
            "default": ConnectionConfig(backend="sqlite"),
            "prod": ConnectionConfig(backend="mssql", database="x"),
            "pg": ConnectionConfig(backend="postgresql", database="x"),
        }
    )

    assert [f"{r.connection}.{r.key}" for r in rows] == [
        "default.info",
        "prod.pyodbc",
        "prod.odbc_driver",
        "pg.backend",
    ]
