"""Shared fixtures and helpers for the MSSQL backend tests."""

from __future__ import annotations

import sys
import types
from typing import Any
from unittest.mock import MagicMock

import pytest

from mcp_tools_sql.backends.mssql import _odbc_escape
from mcp_tools_sql.config.models import ConnectionConfig

LEAKY_PASSWORDS = ["plain", "a}b", "Sw0rd}", "{x}", "p;w", " sec "]


@pytest.fixture
def fake_pyodbc(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Replace pyodbc with a fake module exposing connect() returning a Mock."""
    fake = types.ModuleType("pyodbc")
    error_cls = type("Error", (Exception,), {})
    operational_error_cls = type("OperationalError", (error_cls,), {})
    fake.Error = error_cls  # type: ignore[attr-defined]
    fake.OperationalError = operational_error_cls  # type: ignore[attr-defined]
    fake.connect = MagicMock(  # type: ignore[attr-defined]
        return_value=MagicMock(name="connection")
    )
    monkeypatch.setitem(sys.modules, "pyodbc", fake)
    return fake


def _cfg(**kw: Any) -> ConnectionConfig:
    """Build a ConnectionConfig with sensible defaults for tests."""
    base: dict[str, Any] = {
        "backend": "mssql",
        "host": "h",
        "port": 1433,
        "database": "d",
        "username": "u",
        "password": "p",
    }
    base.update(kw)
    return ConnectionConfig(**base)


def assert_no_leak(text: str, password: str) -> None:
    """Assert neither the literal nor the ODBC-escaped password is in *text*."""
    assert password not in text
    assert _odbc_escape(password) not in text
