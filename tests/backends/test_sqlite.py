"""Comprehensive tests for SQLiteBackend."""

from __future__ import annotations

import os
import sqlite3
import stat
import sys
import threading
from pathlib import Path
from typing import Any

import pytest

from mcp_tools_sql.backends.sqlite import SQLiteBackend
from mcp_tools_sql.config.models import ConnectionConfig


def _make_backend(path: str) -> SQLiteBackend:
    """Create a SQLiteBackend from a file path."""
    return SQLiteBackend(ConnectionConfig(backend="sqlite", path=path))


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
# Read-only query execution
# ---------------------------------------------------------------------------


@pytest.mark.sqlite_integration
class TestReadOnlyQuery:
    """Tests for ``SQLiteBackend.execute_readonly_query``."""

    def test_returns_rows_as_dicts(self, sqlite_db: Path) -> None:
        """Parity with execute_query: rows come back as column-keyed dicts."""
        with _make_backend(str(sqlite_db)) as backend:
            ro_rows = backend.execute_readonly_query(
                "SELECT id, name FROM customers ORDER BY id"
            )
            rw_rows = backend.execute_query(
                "SELECT id, name FROM customers ORDER BY id"
            )
            assert ro_rows == rw_rows
            assert isinstance(ro_rows[0], dict)
            assert ro_rows[0] == {"id": 1, "name": "Bank A"}

    def test_accepts_params(self, sqlite_db: Path) -> None:
        with _make_backend(str(sqlite_db)) as backend:
            rows = backend.execute_readonly_query(
                "SELECT name FROM customers WHERE country = :country",
                {"country": "France"},
            )
            assert rows == [{"name": "Bank B"}]

    def test_sees_committed_data(self, sqlite_db: Path) -> None:
        """A fresh connection reads data committed via execute_update."""
        with _make_backend(str(sqlite_db)) as backend:
            backend.execute_update(
                "INSERT INTO customers VALUES (:id, :name, :country)",
                {"id": 3, "name": "Bank C", "country": "Spain"},
            )
            rows = backend.execute_readonly_query(
                "SELECT name FROM customers WHERE id = :id", {"id": 3}
            )
            assert rows == [{"name": "Bank C"}]

    def test_write_is_rejected(self, sqlite_db: Path) -> None:
        """PRAGMA query_only = ON makes writes fail on the fresh connection."""
        with _make_backend(str(sqlite_db)) as backend:
            with pytest.raises(sqlite3.OperationalError):
                backend.execute_readonly_query(
                    "INSERT INTO customers VALUES (4, 'Bank D', 'Italy')"
                )
            # The blocked write never landed.
            rows = backend.execute_query(
                "SELECT COUNT(*) AS n FROM customers WHERE id = 4"
            )
            assert rows == [{"n": 0}]

    def test_persistent_connection_unaffected(self, sqlite_db: Path) -> None:
        """The fresh connection is closed; the backend stays usable."""
        backend = _make_backend(str(sqlite_db))
        backend.connect()
        persistent = backend._connection
        backend.execute_readonly_query("SELECT 1 AS one")
        assert backend._connection is persistent
        rows = backend.execute_query("SELECT 1 AS one")
        assert rows == [{"one": 1}]
        backend.close()

    def test_empty_path_raises(self) -> None:
        backend = SQLiteBackend(ConnectionConfig(backend="sqlite", path=""))
        with pytest.raises(ValueError, match="must not be empty"):
            backend.execute_readonly_query("SELECT 1")


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
        backend = SQLiteBackend(ConnectionConfig(backend="sqlite", path=""))
        with pytest.raises(ValueError, match="must not be empty"):
            backend.connect()

    @pytest.mark.parametrize(
        "method,args",
        _DATA_METHODS,
        ids=[m for m, _ in _DATA_METHODS],
    )
    def test_lazy_connect_on_first_call(
        self, sqlite_db: Path, method: str, args: tuple[Any, ...]
    ) -> None:
        backend = _make_backend(str(sqlite_db))
        getattr(backend, method)(*args)
        assert backend._connection is not None
        backend.close()

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
        with pytest.raises(RuntimeError, match="Backend has been closed"):
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


# ---------------------------------------------------------------------------
# Isolated connection primitive
# ---------------------------------------------------------------------------


@pytest.mark.sqlite_integration
class TestIsolatedConnection:
    """Tests for ``SQLiteBackend.get_isolated_connection``."""

    def test_yields_persistent_connection(self, sqlite_db: Path) -> None:
        backend = _make_backend(str(sqlite_db))
        backend.connect()
        with backend.get_isolated_connection() as conn:
            assert conn is backend._connection
        backend.close()

    def test_persistent_connection_usable_after_exit(self, sqlite_db: Path) -> None:
        backend = _make_backend(str(sqlite_db))
        with backend.get_isolated_connection():
            pass
        rows = backend.execute_query("SELECT 1 AS one")
        assert rows == [{"one": 1}]
        backend.close()

    def test_lazy_connect_on_enter(self, sqlite_db: Path) -> None:
        backend = _make_backend(str(sqlite_db))
        backend.get_isolated_connection()
        assert backend._connection is None
        with backend.get_isolated_connection() as conn:
            assert isinstance(conn, sqlite3.Connection)
        backend.close()


# ---------------------------------------------------------------------------
# Concurrency
# ---------------------------------------------------------------------------


@pytest.mark.sqlite_integration
class TestConcurrency:
    """Thread-safety tests for lazy-connect."""

    def test_concurrent_first_call_connects_once(
        self, sqlite_db: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        real_connect = sqlite3.connect
        call_count = 0
        count_lock = threading.Lock()

        def counting_connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
            nonlocal call_count
            with count_lock:
                call_count += 1
            conn: sqlite3.Connection = real_connect(*args, **kwargs)
            return conn

        monkeypatch.setattr(sqlite3, "connect", counting_connect)

        backend = _make_backend(str(sqlite_db))
        errors: list[BaseException] = []
        barrier = threading.Barrier(5)
        exec_lock = threading.Lock()

        def worker() -> None:
            try:
                barrier.wait()
                backend.connect()
                with exec_lock:
                    backend.execute_query("SELECT 1")
            except BaseException as exc:  # pylint: disable=broad-except
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        assert call_count == 1
        backend.close()
