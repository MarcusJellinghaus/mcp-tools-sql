"""SQLite database backend."""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from mcp_tools_sql.backends.base import DatabaseBackend
from mcp_tools_sql.config.models import ConnectionConfig


class SQLiteBackend(DatabaseBackend):
    """Backend for SQLite databases."""

    def __init__(self, config: ConnectionConfig) -> None:
        self._config = config
        self._connection: sqlite3.Connection | None = None
        self._closed: bool = False
        self._connect_lock = threading.Lock()

    def connect(self) -> None:
        """Open a connection to the SQLite database (lazy, idempotent).

        Raises:
            ValueError: If the connection path is empty.
            RuntimeError: If the backend was already closed.
        """
        if self._connection is not None and not self._closed:
            return
        with self._connect_lock:
            if self._closed:
                msg = "Backend has been closed."
                raise RuntimeError(msg)
            if self._connection is not None:
                return
            path = self._config.path
            if not path:
                msg = "SQLite path must not be empty."
                raise ValueError(msg)
            conn = sqlite3.connect(path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            self._connection = conn

    def close(self) -> None:
        """Close the SQLite connection (idempotent)."""
        if self._connection is not None:
            self._connection.close()
            self._connection = None
        self._closed = True

    def execute_query(
        self, sql: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Execute a SELECT query.

        Returns:
            Rows as a list of dicts.
        """
        self.connect()
        assert self._connection is not None
        cursor = self._connection.execute(sql, params or {})
        return [dict(row) for row in cursor.fetchall()]

    def execute_readonly_query(
        self, sql: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Execute a SELECT on a fresh ``PRAGMA query_only = ON`` connection.

        Opens a brand-new single-use connection to the same database file,
        sets ``query_only`` so the DB rejects any write, runs the query, and
        closes the connection in ``finally``. The persistent connection is
        never touched.

        Returns:
            Rows as a list of dicts.

        Raises:
            ValueError: If the connection path is empty.
        """
        path = self._config.path
        if not path:
            msg = "SQLite path must not be empty."
            raise ValueError(msg)
        conn = sqlite3.connect(path, check_same_thread=False)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA query_only = ON")
            cursor = conn.execute(sql, params or {})
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def execute_update(self, sql: str, params: dict[str, Any] | None = None) -> int:
        """Execute an UPDATE/INSERT.

        Returns:
            Number of affected rows.
        """
        self.connect()
        assert self._connection is not None
        cursor = self._connection.execute(sql, params or {})
        self._connection.commit()
        return cursor.rowcount

    def explain(self, sql: str, params: dict[str, Any] | None = None) -> str:
        """Return the query execution plan.

        SQLite's ``EXPLAIN QUERY PLAN`` requires bound values to compile
        parameterized SQL, so callers must pass ``params`` whenever the SQL
        references ``:name`` placeholders.
        """
        self.connect()
        assert self._connection is not None
        cursor = self._connection.execute(f"EXPLAIN QUERY PLAN {sql}", params or {})
        rows = cursor.fetchall()
        return "\n".join(row["detail"] for row in rows)

    @contextmanager
    def get_isolated_connection(self) -> Iterator[Any]:
        """Yield the persistent connection (no-op isolation for SQLite).

        ``EXPLAIN QUERY PLAN`` does not execute the statement, so reusing the
        persistent connection is safe. Callers MUST NOT close the yielded
        connection.
        """
        self.connect()
        assert self._connection is not None
        yield self._connection
