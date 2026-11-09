"""Tests for `verify_dependencies`."""

from __future__ import annotations

import pytest

from mcp_tools_sql.verification import dependencies, verify_dependencies
from mcp_tools_sql.verification._helpers import checks_ok


def _missing(name: str) -> object:
    """Build a probe that raises ImportError like a missing driver import."""

    def _probe() -> str:
        raise ImportError(f"No module named {name!r}")

    return _probe


def _patch_pyodbc(
    monkeypatch: pytest.MonkeyPatch, version: str, drivers: list[str]
) -> None:
    """Patch the pyodbc probes used by the dependencies section."""
    monkeypatch.setattr(dependencies, "pyodbc_version", lambda: version)
    monkeypatch.setattr(dependencies, "odbc_drivers", lambda: list(drivers))


def test_verify_dependencies_sqlite_shows_info_line() -> None:
    """sqlite backend returns a single OK info entry."""
    result = verify_dependencies("sqlite")

    assert result["info"]["ok"] is True
    assert "no optional dependencies" in result["info"]["value"]
    assert checks_ok(result) is True


def test_verify_dependencies_unknown_backend_returns_err() -> None:
    """`unknown` backend returns ok=False with a clear error message."""
    result = verify_dependencies("unknown")

    assert checks_ok(result) is False
    assert result["backend"]["ok"] is False
    assert "cannot determine backend" in result["backend"]["error"]


def test_verify_dependencies_postgresql_when_psycopg_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """postgresql branch reports ok=False with install_hint when psycopg missing."""
    monkeypatch.setattr(dependencies, "psycopg_version", _missing("psycopg"))

    result = verify_dependencies("postgresql")

    assert result["psycopg"]["ok"] is False
    assert "(not installed)" in result["psycopg"]["value"]
    assert "pip install" in result["psycopg"]["install_hint"]
    assert checks_ok(result) is False


def test_verify_dependencies_mssql_when_pyodbc_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """mssql branch reports ok=False for pyodbc when missing, and skips driver."""
    monkeypatch.setattr(dependencies, "pyodbc_version", _missing("pyodbc"))

    result = verify_dependencies("mssql")

    assert result["pyodbc"]["ok"] is False
    assert "pip install mcp-tools-sql[mssql]" in result["pyodbc"]["install_hint"]
    assert result["odbc_driver"]["ok"] is False
    assert checks_ok(result) is False


def test_verify_dependencies_mssql_with_pyodbc_and_driver(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """mssql branch returns ok when pyodbc present and a SQL Server driver exists."""
    _patch_pyodbc(
        monkeypatch, "5.0.1", ["ODBC Driver 18 for SQL Server", "Other Driver"]
    )

    result = verify_dependencies("mssql")

    assert result["pyodbc"]["ok"] is True
    assert result["odbc_driver"]["ok"] is True
    assert "SQL Server" in result["odbc_driver"]["value"]
    assert checks_ok(result) is True


def test_verify_dependencies_mssql_with_pyodbc_no_driver(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """mssql branch returns ok=False for driver when no SQL Server driver found."""
    _patch_pyodbc(monkeypatch, "5.0.1", ["SQLite ODBC Driver"])

    result = verify_dependencies("mssql")

    assert result["pyodbc"]["ok"] is True
    assert result["odbc_driver"]["ok"] is False
    assert "ODBC Driver 18 for SQL Server" in result["odbc_driver"]["install_hint"]
    assert checks_ok(result) is False


def test_verify_dependencies_mssql_configured_driver_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """configured_driver present in installed list → odbc_driver row OK with that name."""
    _patch_pyodbc(
        monkeypatch,
        "5.0.1",
        ["ODBC Driver 17 for SQL Server", "ODBC Driver 18 for SQL Server"],
    )

    result = verify_dependencies(
        "mssql", configured_driver="ODBC Driver 18 for SQL Server"
    )

    assert result["odbc_driver"]["ok"] is True
    assert result["odbc_driver"]["value"] == "ODBC Driver 18 for SQL Server"


def test_verify_dependencies_mssql_configured_driver_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """configured_driver not installed → odbc_driver row fails and lists installed."""
    _patch_pyodbc(
        monkeypatch,
        "5.0.1",
        ["ODBC Driver 18 for SQL Server", "SQLite ODBC Driver"],
    )

    result = verify_dependencies(
        "mssql", configured_driver="ODBC Driver 17 for SQL Server"
    )

    assert result["odbc_driver"]["ok"] is False
    assert "ODBC Driver 17 for SQL Server" in result["odbc_driver"]["value"]
    # Installed drivers shown in the error so the user sees the diff
    assert "ODBC Driver 18 for SQL Server" in result["odbc_driver"]["error"]
    assert "SQLite ODBC Driver" in result["odbc_driver"]["error"]
    assert checks_ok(result) is False
