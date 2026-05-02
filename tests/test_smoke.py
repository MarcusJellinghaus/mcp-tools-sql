"""Smoke tests to verify the project skeleton works."""

from __future__ import annotations

from mcp_tools_sql.config.models import (
    ConnectionConfig,
    DatabaseConfig,
    QueryConfig,
    UpdateConfig,
)


def test_import_version() -> None:
    """Package is importable and exposes a version string."""
    import mcp_tools_sql

    assert isinstance(mcp_tools_sql.__version__, str)


def test_connection_config_defaults() -> None:
    """ConnectionConfig has sensible defaults."""
    cfg = ConnectionConfig()
    assert cfg.backend == "sqlite"
    assert cfg.host == ""
    assert cfg.port == 0


def test_database_config_empty() -> None:
    """DatabaseConfig can be constructed with no arguments."""
    cfg = DatabaseConfig()
    assert cfg.connections == {}
    assert cfg.security.allow_updates is True


def test_query_config_minimal() -> None:
    """QueryConfig only requires sql."""
    qc = QueryConfig(sql="SELECT 1")
    assert qc.sql == "SELECT 1"
    assert qc.max_rows == 100


def test_update_config_minimal() -> None:
    """UpdateConfig can be constructed with defaults."""
    uc = UpdateConfig()
    assert uc.table == ""
    assert uc.fields == []


def test_create_backend_sqlite(tmp_path: object) -> None:
    """create_backend returns an SQLiteBackend for backend='sqlite'."""
    from mcp_tools_sql.backends.base import create_backend

    cfg = ConnectionConfig(backend="sqlite", path=":memory:")
    backend = create_backend(cfg)
    assert type(backend).__name__ == "SQLiteBackend"


def test_create_backend_unknown() -> None:
    """create_backend raises ValueError for unknown backends."""
    import pytest

    from mcp_tools_sql.backends.base import create_backend

    cfg = ConnectionConfig(backend="unknown")
    with pytest.raises(ValueError, match="Unsupported backend"):
        create_backend(cfg)
