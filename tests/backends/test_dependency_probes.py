"""Tests for the driver dependency probes in the backends."""

from __future__ import annotations

import importlib
import sys
import types

import pytest

from mcp_tools_sql.backends.mssql import odbc_drivers, pyodbc_version
from mcp_tools_sql.backends.postgresql import psycopg_version


def _fake_pyodbc(monkeypatch: pytest.MonkeyPatch) -> types.ModuleType:
    """Install a fake pyodbc module exposing ``version`` and ``drivers()``."""
    fake = types.ModuleType("pyodbc")
    fake.version = "5.1.0"  # type: ignore[attr-defined]
    fake.drivers = lambda: [  # type: ignore[attr-defined]
        "ODBC Driver 18 for SQL Server"
    ]
    monkeypatch.setitem(sys.modules, "pyodbc", fake)
    return fake


def test_pyodbc_version_reads_module_version(monkeypatch: pytest.MonkeyPatch) -> None:
    """pyodbc_version returns the driver's version string."""
    _fake_pyodbc(monkeypatch)

    assert pyodbc_version() == "5.1.0"


def test_odbc_drivers_lists_installed_drivers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """odbc_drivers returns pyodbc.drivers() as a list."""
    _fake_pyodbc(monkeypatch)

    assert odbc_drivers() == ["ODBC Driver 18 for SQL Server"]


def test_pyodbc_version_raises_import_error_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing pyodbc surfaces as ImportError."""
    monkeypatch.setitem(sys.modules, "pyodbc", None)

    with pytest.raises(ImportError):
        pyodbc_version()


def test_odbc_drivers_propagates_driver_error_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An error from pyodbc.drivers() propagates as the same object."""
    fake = _fake_pyodbc(monkeypatch)
    boom = RuntimeError("odbc boom")

    def _raise() -> list[str]:
        raise boom

    fake.drivers = _raise  # type: ignore[attr-defined]

    with pytest.raises(RuntimeError) as excinfo:
        odbc_drivers()
    assert excinfo.value is boom


def test_psycopg_version_reads_dunder_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """psycopg_version returns the driver's __version__ string."""
    fake = types.ModuleType("psycopg")
    fake.__version__ = "3.2.1"  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "psycopg", fake)

    assert psycopg_version() == "3.2.1"


def test_psycopg_version_raises_import_error_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing psycopg surfaces as ImportError."""
    monkeypatch.setitem(sys.modules, "psycopg", None)

    with pytest.raises(ImportError):
        psycopg_version()


def test_postgresql_module_imports_without_psycopg(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """backends.postgresql imports cleanly when psycopg is not installed."""
    monkeypatch.setitem(sys.modules, "psycopg", None)
    monkeypatch.delitem(sys.modules, "mcp_tools_sql.backends.postgresql")

    module = importlib.import_module("mcp_tools_sql.backends.postgresql")

    assert callable(module.psycopg_version)
