"""Tests for `verify_dependencies`."""

from __future__ import annotations

import pytest

from mcp_tools_sql.backends import connection_check
from mcp_tools_sql.backends.connection_check import MSSQL_INSTALL_HINT
from mcp_tools_sql.config.models import ConnectionConfig, DatabaseConfig
from mcp_tools_sql.verification import verify_dependencies
from mcp_tools_sql.verification._helpers import checks_ok


def _missing_pyodbc() -> str:
    """Probe that raises like a missing pyodbc import."""
    raise ImportError("No module named 'pyodbc'")


@pytest.mark.parametrize("db_config", [None, DatabaseConfig()])
def test_no_connections_yields_single_backend_row(
    db_config: DatabaseConfig | None,
) -> None:
    """No config, or one without connections → the single ``backend`` ERR row."""
    result = verify_dependencies(db_config)

    assert list(result) == ["backend"]
    assert result["backend"]["ok"] is False
    assert "cannot determine backend" in result["backend"]["error"]
    assert checks_ok(result) is False


def test_rows_are_keyed_per_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every connection gets its own ``<connection>.<key>`` rows."""
    monkeypatch.setattr(connection_check, "pyodbc_version", lambda: "5.1.0")
    monkeypatch.setattr(
        connection_check, "odbc_drivers", lambda: ["ODBC Driver 18 for SQL Server"]
    )
    db_config = DatabaseConfig(
        connections={
            "default": ConnectionConfig(backend="sqlite"),
            "prod": ConnectionConfig(backend="mssql", database="x"),
        }
    )

    result = verify_dependencies(db_config)

    assert list(result) == ["default.info", "prod.pyodbc", "prod.odbc_driver"]
    assert result["prod.pyodbc"]["value"] == "5.1.0"
    assert checks_ok(result) is True


def test_hint_is_mapped_to_install_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    """A row's hint becomes the entry's ``install_hint``."""
    monkeypatch.setattr(connection_check, "pyodbc_version", _missing_pyodbc)
    db_config = DatabaseConfig(
        connections={"prod": ConnectionConfig(backend="mssql", database="x")}
    )

    result = verify_dependencies(db_config)

    assert result["prod.pyodbc"]["ok"] is False
    assert result["prod.pyodbc"]["install_hint"] == MSSQL_INSTALL_HINT
    assert result["prod.odbc_driver"]["value"] == "(skipped)"
    assert checks_ok(result) is False
