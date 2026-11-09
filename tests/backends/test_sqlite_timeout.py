"""Tests for the SQLite statement timeout (``_statement_deadline``)."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest

from mcp_tools_sql.backends.base import (
    BackendConnectionError,
    Deadline,
    QueryTimeoutError,
)
from mcp_tools_sql.backends.sqlite import SQLiteBackend, _statement_deadline
from mcp_tools_sql.config.models import ConnectionConfig

_SLOW_SQL = (
    "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM c) "
    "SELECT x FROM c LIMIT 500000000"
)


@pytest.fixture
def backend(tmp_path: Path) -> SQLiteBackend:
    """A backend over a one-table file DB with a 1 s statement timeout."""
    path = tmp_path / "t.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v INTEGER)")
    conn.execute("INSERT INTO t (id, v) VALUES (1, 0)")
    conn.commit()
    conn.close()
    return SQLiteBackend(
        ConnectionConfig(backend="sqlite", path=str(path), query_timeout_seconds=1)
    )


@pytest.mark.sqlite_integration
class TestStatementTimeout:
    """Every statement path aborts with ``QueryTimeoutError``."""

    def test_readonly_query_times_out(self, backend: SQLiteBackend) -> None:
        start = time.monotonic()
        with pytest.raises(QueryTimeoutError) as info:
            backend.execute_readonly_query(_SLOW_SQL)
        assert time.monotonic() - start < 3
        assert info.value.seconds == 1

    def test_readonly_query_with_columns_times_out(
        self, backend: SQLiteBackend
    ) -> None:
        with pytest.raises(QueryTimeoutError):
            backend.execute_readonly_query_with_columns(_SLOW_SQL)

    def test_execute_query_times_out(self, backend: SQLiteBackend) -> None:
        with pytest.raises(QueryTimeoutError):
            backend.execute_query(_SLOW_SQL)
        backend.close()

    def test_execute_update_times_out(self, backend: SQLiteBackend) -> None:
        sql = (
            "UPDATE t SET v = (WITH RECURSIVE c(x) AS "
            "(SELECT 1 UNION ALL SELECT x+1 FROM c LIMIT 500000000) "
            "SELECT max(x) FROM c) WHERE id = 1"
        )
        with pytest.raises(QueryTimeoutError):
            backend.execute_update(sql)
        backend.close()

    def test_persistent_connection_usable_after_timeout(
        self, backend: SQLiteBackend
    ) -> None:
        with pytest.raises(QueryTimeoutError):
            backend.execute_query(_SLOW_SQL)
        assert backend.execute_query("SELECT v FROM t") == [{"v": 0}]
        backend.close()

    def test_non_timeout_error_passes_through(self, backend: SQLiteBackend) -> None:
        with pytest.raises(BackendConnectionError) as info:
            backend.execute_query("SELECT * FROM missing_table")
        assert info.value.original_class == "OperationalError"
        backend.close()


def test_counting_deadline_interrupts_first() -> None:
    conn = sqlite3.connect(":memory:")
    try:
        start = time.monotonic()
        with pytest.raises(QueryTimeoutError):
            with _statement_deadline(conn, 30, Deadline(at=time.monotonic())):
                conn.execute(_SLOW_SQL).fetchall()
        assert time.monotonic() - start < 3
    finally:
        conn.close()


def test_unarmed_counting_deadline_is_ignored() -> None:
    conn = sqlite3.connect(":memory:")
    try:
        with _statement_deadline(conn, 30, Deadline()):
            rows = conn.execute("SELECT 1").fetchall()
        assert rows == [(1,)]
    finally:
        conn.close()
