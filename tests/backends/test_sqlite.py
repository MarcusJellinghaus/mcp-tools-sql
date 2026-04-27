"""Comprehensive tests for SQLiteBackend."""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path
from typing import Any

import pytest

from mcp_tools_sql.backends.sqlite import SQLiteBackend
from mcp_tools_sql.config.models import ConnectionConfig


def _make_backend(path: str) -> SQLiteBackend:
    """Create a SQLiteBackend from a file path."""
    return SQLiteBackend(ConnectionConfig(backend="sqlite", connection_string=path))


# ---------------------------------------------------------------------------
# Connection & context manager
# ---------------------------------------------------------------------------


@pytest.mark.sqlite_integration
class TestConnection:
    """Connection lifecycle tests."""

    def test_connect_and_close(self, sqlite_db: Path) -> None:
        backend = _make_backend(str(sqlite_db))
        backend.connect()
        # Verify operational
        rows = backend.execute_query(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        assert len(rows) > 0
        backend.close()
        # Verify closed
        with pytest.raises(RuntimeError):
            backend.execute_query("SELECT 1")

    def test_connect_idempotent(self, sqlite_db: Path) -> None:
        backend = _make_backend(str(sqlite_db))
        backend.connect()
        backend.connect()  # second call is a no-op
        rows = backend.execute_query(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        names = [r["name"] for r in rows]
        assert "customers" in names
        backend.close()

    def test_close_idempotent(self, sqlite_db: Path) -> None:
        backend = _make_backend(str(sqlite_db))
        backend.connect()
        backend.close()
        backend.close()  # second call doesn't raise

    def test_context_manager(self, sqlite_db: Path) -> None:
        backend = _make_backend(str(sqlite_db))
        with backend:
            rows = backend.execute_query(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            names = [r["name"] for r in rows]
            assert "customers" in names
        # After exit, connection is closed
        with pytest.raises(RuntimeError):
            backend.execute_query("SELECT 1")

    def test_context_manager_returns_backend(self, sqlite_db: Path) -> None:
        backend = _make_backend(str(sqlite_db))
        with backend as b:
            assert b is backend


# ---------------------------------------------------------------------------
# Query execution
# ---------------------------------------------------------------------------


@pytest.mark.sqlite_integration
class TestQueryExecution:
    """Query execution tests."""

    def test_execute_query(self, sqlite_db: Path) -> None:
        with _make_backend(str(sqlite_db)) as backend:
            rows = backend.execute_query(
                "SELECT name FROM customers WHERE country = :country",
                {"country": "Germany"},
            )
            assert len(rows) == 1
            assert rows[0]["name"] == "Bank A"

    def test_execute_query_no_params(self, sqlite_db: Path) -> None:
        with _make_backend(str(sqlite_db)) as backend:
            rows = backend.execute_query("SELECT id, name FROM customers ORDER BY id")
            assert len(rows) == 2
            assert isinstance(rows[0], dict)
            assert rows[0]["id"] == 1

    def test_execute_update(self, sqlite_db: Path) -> None:
        with _make_backend(str(sqlite_db)) as backend:
            rowcount = backend.execute_update(
                "INSERT INTO customers VALUES (:id, :name, :country)",
                {"id": 3, "name": "Bank C", "country": "Spain"},
            )
            assert rowcount == 1
            rows = backend.execute_query(
                "SELECT name FROM customers WHERE id = :id", {"id": 3}
            )
            assert rows[0]["name"] == "Bank C"

    def test_explain(self, sqlite_db: Path) -> None:
        with _make_backend(str(sqlite_db)) as backend:
            plan = backend.explain("SELECT * FROM customers")
            assert isinstance(plan, str)
            assert len(plan) > 0


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

# Methods that require a connection and their call arguments
_DATA_METHODS: list[tuple[str, tuple[Any, ...]]] = [
    ("execute_query", ("SELECT 1",)),
    ("execute_update", ("SELECT 1",)),
    ("explain", ("SELECT 1",)),
]


@pytest.mark.sqlite_integration
class TestErrorHandling:
    """Error handling tests."""

    def test_connect_empty_path(self) -> None:
        backend = SQLiteBackend(
            ConnectionConfig(backend="sqlite", connection_string="")
        )
        with pytest.raises(ValueError, match="must not be empty"):
            backend.connect()

    @pytest.mark.parametrize(
        "method,args",
        _DATA_METHODS,
        ids=[m for m, _ in _DATA_METHODS],
    )
    def test_operations_before_connect(
        self, tmp_path: Path, method: str, args: tuple[Any, ...]
    ) -> None:
        backend = _make_backend(str(tmp_path / "unused.db"))
        with pytest.raises(RuntimeError, match="Not connected"):
            getattr(backend, method)(*args)

    @pytest.mark.parametrize(
        "method,args",
        _DATA_METHODS,
        ids=[m for m, _ in _DATA_METHODS],
    )
    def test_operations_after_close(
        self, sqlite_db: Path, method: str, args: tuple[Any, ...]
    ) -> None:
        backend = _make_backend(str(sqlite_db))
        backend.connect()
        backend.close()
        with pytest.raises(RuntimeError, match="Not connected"):
            getattr(backend, method)(*args)

    def test_connect_invalid_path(self, tmp_path: Path) -> None:
        invalid_path = str(tmp_path / "nonexistent_dir" / "sub" / "test.db")
        backend = _make_backend(invalid_path)
        with pytest.raises(Exception):
            backend.connect()

    @pytest.mark.skipif(sys.platform == "win32", reason="chmod not reliable on Windows")
    def test_connect_readonly_file(self, tmp_path: Path) -> None:
        db_path = tmp_path / "readonly.db"
        db_path.touch()
        os.chmod(db_path, stat.S_IRUSR)
        try:
            backend = _make_backend(str(db_path))
            backend.connect()
            with pytest.raises(Exception):
                backend.execute_update("CREATE TABLE t (id INTEGER PRIMARY KEY)")
        finally:
            os.chmod(db_path, stat.S_IRUSR | stat.S_IWUSR)

    def test_connect_corrupt_db(self, tmp_path: Path) -> None:
        corrupt_path = tmp_path / "corrupt.db"
        corrupt_path.write_bytes(b"this is not a valid sqlite database file!!!")
        backend = _make_backend(str(corrupt_path))
        backend.connect()
        with pytest.raises(Exception):
            backend.execute_query("SELECT name FROM sqlite_master WHERE type='table'")
