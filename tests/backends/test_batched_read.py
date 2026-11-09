"""Tests for ``DatabaseBackend.iter_readonly_batches``."""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from mcp_tools_sql.backends.base import (
    FETCH_BATCH_SIZE,
    DatabaseBackend,
    Deadline,
    QueryTimeoutError,
)
from mcp_tools_sql.backends.mssql import MSSQLBackend
from mcp_tools_sql.backends.sqlite import SQLiteBackend
from mcp_tools_sql.config.models import ConnectionConfig
from tests.backends.conftest import _cfg

_ROW_COUNT = 1201
_EXPECTED_SIZES = [500, 500, 201]

_SLOW_SQL = (
    "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM c) "
    "SELECT x FROM c LIMIT 500000000"
)


class _FakeBackend(DatabaseBackend):
    """Minimal backend whose read-only query returns a fixed row list."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def connect(self) -> None:
        pass

    def close(self) -> None:
        pass

    def execute_query(
        self, sql: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        return self._rows

    def execute_readonly_query(
        self, sql: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        return self._rows

    def execute_readonly_query_with_columns(
        self, sql: str, params: dict[str, Any] | None = None
    ) -> tuple[list[str], list[tuple[Any, ...]]]:
        return [], []

    def execute_update(self, sql: str, params: dict[str, Any] | None = None) -> int:
        return 0

    def explain(self, sql: str, params: dict[str, Any] | None = None) -> str:
        return ""

    @contextmanager
    def get_isolated_connection(self) -> Iterator[Any]:
        yield None


def test_batch_size_constant() -> None:
    assert FETCH_BATCH_SIZE == 500


def test_base_default_chunks_readonly_query() -> None:
    rows = [{"id": i} for i in range(_ROW_COUNT)]
    batches = list(_FakeBackend(rows).iter_readonly_batches("SELECT 1"))
    assert [len(b) for b in batches] == _EXPECTED_SIZES
    assert [r for b in batches for r in b] == rows


def test_base_default_empty_result_yields_nothing() -> None:
    assert not list(_FakeBackend([]).iter_readonly_batches("SELECT 1"))


@pytest.fixture
def sqlite_backend(tmp_path: Path) -> SQLiteBackend:
    """A backend over a table with 1,201 rows and a 1 s statement timeout."""
    path = tmp_path / "t.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
    conn.executemany(
        "INSERT INTO t (id, v) VALUES (?, ?)",
        [(i, f"v{i}") for i in range(_ROW_COUNT)],
    )
    conn.commit()
    conn.close()
    return SQLiteBackend(
        ConnectionConfig(backend="sqlite", path=str(path), query_timeout_seconds=1)
    )


@pytest.mark.sqlite_integration
class TestSQLiteBatches:
    """SQLite fetches with ``fetchmany`` on a fresh read-only connection."""

    def test_batch_sizes_and_dict_rows(self, sqlite_backend: SQLiteBackend) -> None:
        batches = list(
            sqlite_backend.iter_readonly_batches("SELECT id, v FROM t ORDER BY id")
        )
        assert [len(b) for b in batches] == _EXPECTED_SIZES
        assert batches[0][0] == {"id": 0, "v": "v0"}
        assert batches[2][-1] == {"id": 1200, "v": "v1200"}

    def test_params_are_bound(self, sqlite_backend: SQLiteBackend) -> None:
        batches = list(
            sqlite_backend.iter_readonly_batches(
                "SELECT id FROM t WHERE id < :n", {"n": 3}
            )
        )
        assert batches == [[{"id": 0}, {"id": 1}, {"id": 2}]]

    def test_writes_rejected(self, sqlite_backend: SQLiteBackend) -> None:
        with pytest.raises(sqlite3.OperationalError):
            list(sqlite_backend.iter_readonly_batches("DELETE FROM t"))

    def test_close_after_first_batch_closes_connection(
        self, sqlite_backend: SQLiteBackend, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        opened: list[sqlite3.Connection] = []
        real_connect = sqlite3.connect

        def _recording_connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
            conn: sqlite3.Connection = real_connect(*args, **kwargs)
            opened.append(conn)
            return conn

        monkeypatch.setattr(sqlite3, "connect", _recording_connect)
        gen = sqlite_backend.iter_readonly_batches("SELECT id FROM t")
        assert len(next(gen)) == FETCH_BATCH_SIZE
        gen.close()
        assert len(opened) == 1
        with pytest.raises(sqlite3.ProgrammingError):
            opened[0].execute("SELECT 1")

    def test_statement_timeout_during_fetch(
        self, sqlite_backend: SQLiteBackend
    ) -> None:
        gen = sqlite_backend.iter_readonly_batches(_SLOW_SQL)
        start = time.monotonic()
        assert len(next(gen)) == FETCH_BATCH_SIZE
        with pytest.raises(QueryTimeoutError) as info:
            for _ in gen:
                pass
        assert time.monotonic() - start < 3
        assert info.value.seconds == 1

    def test_counting_deadline_stops_mid_fetch(self, tmp_path: Path) -> None:
        backend = SQLiteBackend(
            ConnectionConfig(
                backend="sqlite",
                path=str(tmp_path / "e.db"),
                query_timeout_seconds=30,
            )
        )
        counting = Deadline()
        gen = backend.iter_readonly_batches(_SLOW_SQL, counting=counting)
        assert len(next(gen)) == FETCH_BATCH_SIZE
        counting.at = time.monotonic()
        start = time.monotonic()
        with pytest.raises(QueryTimeoutError):
            for _ in gen:
                pass
        assert time.monotonic() - start < 3


class TestMSSQLBatches:
    """SQL Server fetches with ``fetchmany`` on the persistent connection."""

    def test_batches_until_empty(self, fake_pyodbc: Any) -> None:
        cur = fake_pyodbc.connect.return_value.cursor.return_value
        cur.description = [("a",), ("b",)]
        cur.fetchmany.side_effect = [[(1, "x"), (2, "y")], [(3, "z")], []]
        b = MSSQLBackend(_cfg())
        batches = list(b.iter_readonly_batches("SELECT a, b FROM t"))
        assert batches == [
            [{"a": 1, "b": "x"}, {"a": 2, "b": "y"}],
            [{"a": 3, "b": "z"}],
        ]
        cur.fetchmany.assert_called_with(FETCH_BATCH_SIZE)
        cur.close.assert_called_once()

    def test_params_translated_to_qmark(self, fake_pyodbc: Any) -> None:
        cur = fake_pyodbc.connect.return_value.cursor.return_value
        cur.description = [("a",)]
        cur.fetchmany.side_effect = [[]]
        b = MSSQLBackend(_cfg())
        assert not list(
            b.iter_readonly_batches("SELECT a FROM t WHERE a = :x", {"x": 7})
        )
        sql, args = cur.execute.call_args.args
        assert "?" in sql
        assert args == [7]

    def test_close_after_first_batch_closes_cursor(self, fake_pyodbc: Any) -> None:
        cur = fake_pyodbc.connect.return_value.cursor.return_value
        cur.description = [("a",)]
        cur.fetchmany.side_effect = [[(1,)], [(2,)], []]
        b = MSSQLBackend(_cfg())
        gen = b.iter_readonly_batches("SELECT a FROM t")
        assert next(gen) == [{"a": 1}]
        cur.close.assert_not_called()
        gen.close()
        cur.close.assert_called_once()

    def test_fetch_hyt00_raises_query_timeout(self, fake_pyodbc: Any) -> None:
        cur = fake_pyodbc.connect.return_value.cursor.return_value
        cur.description = [("a",)]
        cur.fetchmany.side_effect = [
            [(1,)],
            fake_pyodbc.OperationalError("HYT00", "timeout"),
        ]
        b = MSSQLBackend(_cfg(query_timeout_seconds=5))
        gen = b.iter_readonly_batches("SELECT a FROM t")
        assert next(gen) == [{"a": 1}]
        with pytest.raises(QueryTimeoutError) as info:
            next(gen)
        assert info.value.seconds == 5
        cur.close.assert_called_once()
