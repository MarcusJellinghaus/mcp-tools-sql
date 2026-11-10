"""Tests for the supported-backend set and alias normalisation in backends/base."""

from __future__ import annotations

import pytest

from mcp_tools_sql.backends.base import SUPPORTED_BACKENDS, normalize_backend


def test_supported_backends() -> None:
    assert {"sqlite", "mssql", "pyodbc"} == SUPPORTED_BACKENDS


def test_normalize_backend_maps_pyodbc_to_mssql() -> None:
    assert normalize_backend("pyodbc") == "mssql"


@pytest.mark.parametrize("name", ["mssql", "sqlite", "postgresql"])
def test_normalize_backend_leaves_other_names_unchanged(name: str) -> None:
    assert normalize_backend(name) == name
