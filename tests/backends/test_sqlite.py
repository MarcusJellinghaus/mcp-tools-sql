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
        tables = backend.read_tables("main")
        assert len(tables) > 0
        backend.close()
        # Verify closed
        with pytest.raises(RuntimeError):
            backend.read_tables("main")

    def test_connect_idempotent(self, sqlite_db: Path) -> None:
        backend = _make_backend(str(sqlite_db))
        backend.connect()
        backend.connect()  # second call is a no-op
        tables = backend.read_tables("main")
        assert "customers" in tables
        backend.close()

    def test_close_idempotent(self, sqlite_db: Path) -> None:
        backend = _make_backend(str(sqlite_db))
        backend.connect()
        backend.close()
        backend.close()  # second call doesn't raise

    def test_context_manager(self, sqlite_db: Path) -> None:
        backend = _make_backend(str(sqlite_db))
        with backend:
            tables = backend.read_tables("main")
            assert "customers" in tables
        # After exit, connection is closed
        with pytest.raises(RuntimeError):
            backend.read_tables("main")

    def test_context_manager_returns_backend(self, sqlite_db: Path) -> None:
        backend = _make_backend(str(sqlite_db))
        with backend as b:
            assert b is backend


# ---------------------------------------------------------------------------
# Schema introspection
# ---------------------------------------------------------------------------


@pytest.mark.sqlite_integration
class TestSchemaIntrospection:
    """Schema introspection tests."""

    def test_read_schemas(self, sqlite_db: Path) -> None:
        with _make_backend(str(sqlite_db)) as backend:
            schemas = backend.read_schemas()
            assert schemas == ["main"]

    def test_read_tables(self, sqlite_db: Path) -> None:
        with _make_backend(str(sqlite_db)) as backend:
            tables = backend.read_tables("main")
            assert "customers" in tables
            assert "orders" in tables
            # sqlite internal tables should be excluded
            for t in tables:
                assert not t.startswith("sqlite_")

    def test_read_columns(self, sqlite_db: Path) -> None:
        with _make_backend(str(sqlite_db)) as backend:
            columns = backend.read_columns("main", "customers")
            assert len(columns) == 3
            expected_keys = {"name", "type", "nullable", "default", "is_primary_key"}
            for col in columns:
                assert set(col.keys()) == expected_keys
            names = [c["name"] for c in columns]
            assert names == ["id", "name", "country"]

    def test_read_columns_with_filter(self, sqlite_db: Path) -> None:
        with _make_backend(str(sqlite_db)) as backend:
            columns = backend.read_columns("main", "customers", filter_pattern="na*")
            names = [c["name"] for c in columns]
            assert "name" in names
            assert "id" not in names

    def test_read_columns_filter_no_match(self, sqlite_db: Path) -> None:
        with _make_backend(str(sqlite_db)) as backend:
            columns = backend.read_columns(
                "main", "customers", filter_pattern="zzz_no_match*"
            )
            assert columns == []

    def test_read_relations(self, sqlite_db: Path) -> None:
        with _make_backend(str(sqlite_db)) as backend:
            relations = backend.read_relations("main", "orders")
            assert len(relations) >= 1
            expected_keys = {
                "constraint_name",
                "column",
                "referenced_table",
                "referenced_column",
                "on_update",
                "on_delete",
            }
            rel = relations[0]
            assert set(rel.keys()) == expected_keys
            assert rel["column"] == "customer_id"
            assert rel["referenced_table"] == "customers"
            assert rel["referenced_column"] == "id"

    def test_read_relations_no_fks(self, sqlite_db: Path) -> None:
        with _make_backend(str(sqlite_db)) as backend:
            relations = backend.read_relations("main", "customers")
            assert relations == []


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
    ("read_tables", ("main",)),
    ("read_columns", ("main", "customers")),
    ("read_relations", ("main", "customers")),
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

    def test_read_columns_nonexistent_table(self, sqlite_db: Path) -> None:
        with _make_backend(str(sqlite_db)) as backend:
            # SQLite PRAGMA table_info returns empty for non-existent tables
            columns = backend.read_columns("main", "nonexistent_table")
            assert columns == []

    def test_read_tables_nonexistent_schema(self, sqlite_db: Path) -> None:
        with _make_backend(str(sqlite_db)) as backend:
            # SQLite ignores schema parameter — returns tables regardless
            tables = backend.read_tables("nonexistent_schema")
            assert "customers" in tables

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
            backend.read_tables("main")
