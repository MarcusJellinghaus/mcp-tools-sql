"""Tests for `verify_dependencies`."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

from mcp_tools_sql.verification import verify_dependencies


def test_verify_dependencies_sqlite_shows_info_line() -> None:
    """sqlite backend returns a single OK info entry."""
    result = verify_dependencies("sqlite")

    assert result["info"]["ok"] is True
    assert "no optional dependencies" in result["info"]["value"]
    assert result["overall_ok"] is True


def test_verify_dependencies_unknown_backend_returns_err() -> None:
    """`unknown` backend returns ok=False with a clear error message."""
    result = verify_dependencies("unknown")

    assert result["overall_ok"] is False
    assert result["backend"]["ok"] is False
    assert "cannot determine backend" in result["backend"]["error"]


def test_verify_dependencies_postgresql_when_psycopg_missing() -> None:
    """postgresql branch reports ok=False with install_hint when psycopg missing."""
    with patch.dict(sys.modules, {"psycopg": None}):
        result = verify_dependencies("postgresql")

    assert result["psycopg"]["ok"] is False
    assert "(not installed)" in result["psycopg"]["value"]
    assert "pip install" in result["psycopg"]["install_hint"]
    assert result["overall_ok"] is False


def test_verify_dependencies_mssql_when_pyodbc_missing() -> None:
    """mssql branch reports ok=False for pyodbc when missing, and skips driver."""
    with patch.dict(sys.modules, {"pyodbc": None}):
        result = verify_dependencies("mssql")

    assert result["pyodbc"]["ok"] is False
    assert "pip install mcp-tools-sql[mssql]" in result["pyodbc"]["install_hint"]
    assert result["odbc_driver"]["ok"] is False
    assert result["overall_ok"] is False


def test_verify_dependencies_mssql_with_pyodbc_and_driver() -> None:
    """mssql branch returns ok when pyodbc present and a SQL Server driver exists."""
    fake_pyodbc = MagicMock()
    fake_pyodbc.version = "5.0.1"
    fake_pyodbc.drivers = MagicMock(
        return_value=["ODBC Driver 18 for SQL Server", "Other Driver"]
    )
    with patch.dict(sys.modules, {"pyodbc": fake_pyodbc}):
        result = verify_dependencies("mssql")

    assert result["pyodbc"]["ok"] is True
    assert result["odbc_driver"]["ok"] is True
    assert "SQL Server" in result["odbc_driver"]["value"]
    assert result["overall_ok"] is True


def test_verify_dependencies_mssql_with_pyodbc_no_driver() -> None:
    """mssql branch returns ok=False for driver when no SQL Server driver found."""
    fake_pyodbc = MagicMock()
    fake_pyodbc.version = "5.0.1"
    fake_pyodbc.drivers = MagicMock(return_value=["SQLite ODBC Driver"])
    with patch.dict(sys.modules, {"pyodbc": fake_pyodbc}):
        result = verify_dependencies("mssql")

    assert result["pyodbc"]["ok"] is True
    assert result["odbc_driver"]["ok"] is False
    assert "ODBC Driver 18 for SQL Server" in result["odbc_driver"]["install_hint"]
    assert result["overall_ok"] is False
