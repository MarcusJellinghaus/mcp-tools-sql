"""SQLite database backend."""

from __future__ import annotations

import sqlite3
from typing import Any

from mcp_tools_sql.backends.base import DatabaseBackend
from mcp_tools_sql.config.models import ConnectionConfig


class SQLiteBackend(DatabaseBackend):
    """Backend for SQLite databases."""

    def __init__(self, config: ConnectionConfig) -> None:
        self._config = config
        self._connection: sqlite3.Connection | None = None

    def _require_connection(self) -> sqlite3.Connection:
        """Return the active connection or raise.

        Returns:
            The active SQLite connection.

        Raises:
            RuntimeError: If not connected.
        """
        if self._connection is None:
            msg = "Not connected. Call connect() first."
            raise RuntimeError(msg)
        return self._connection

    def connect(self) -> None:
        """Open a connection to the SQLite database.

        Raises:
            ValueError: If the connection path is empty.
        """
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
        """Close the SQLite connection."""
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def execute_query(
        self, sql: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Execute a SELECT query.

        Returns:
            Rows as a list of dicts.
        """
        conn = self._require_connection()
        cursor = conn.execute(sql, params or {})
        return [dict(row) for row in cursor.fetchall()]

    def execute_update(self, sql: str, params: dict[str, Any] | None = None) -> int:
        """Execute an UPDATE/INSERT.

        Returns:
            Number of affected rows.
        """
        conn = self._require_connection()
        cursor = conn.execute(sql, params or {})
        conn.commit()
        return cursor.rowcount

    def explain(self, sql: str) -> str:
        """Return the query execution plan."""
        conn = self._require_connection()
        cursor = conn.execute(f"EXPLAIN QUERY PLAN {sql}")
        rows = cursor.fetchall()
        return "\n".join(row["detail"] for row in rows)
