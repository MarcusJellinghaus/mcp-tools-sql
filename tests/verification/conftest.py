"""Shared fixtures for verification tests."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest

from mcp_tools_sql.backends.sqlite import SQLiteBackend
from mcp_tools_sql.config.models import ConnectionConfig


@pytest.fixture
def sqlite_backend(sqlite_db: Path) -> Generator[SQLiteBackend, None, None]:
    """Open a connected SQLiteBackend on the shared `sqlite_db` fixture."""
    backend = SQLiteBackend(ConnectionConfig(backend="sqlite", path=str(sqlite_db)))
    backend.connect()
    yield backend
    backend.close()
