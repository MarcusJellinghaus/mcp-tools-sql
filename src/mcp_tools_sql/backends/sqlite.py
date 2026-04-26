"""SQLite database backend."""

from __future__ import annotations

import sqlite3
from fnmatch import fnmatch
from typing import Any

from mcp_tools_sql.backends.base import DatabaseBackend
from mcp_tools_sql.config.models import ConnectionConfig


class SQLiteBackend(DatabaseBackend):
    """Backend for SQLite databases."""

    def __init__(self, config: ConnectionConfig) -> None:
        self._config = config
        self._connection: sqlite3.Connection | None = None

    def _require_connection(self) -> sqlite3.Connection:
        """Return the active connection or raise."""
        if self._connection is None:
            msg = "Not connected. Call connect() first."
            raise RuntimeError(msg)
        return self._connection

    def connect(self) -> None:
        """Open a connection to the SQLite database."""
        if self._connection is not None:
            return
        path = self._config.connection_string
        if not path:
            msg = "SQLite connection path must not be empty."
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
        """Execute a SELECT query."""
        conn = self._require_connection()
        cursor = conn.execute(sql, params or {})
        return [dict(row) for row in cursor.fetchall()]

    def execute_update(self, sql: str, params: dict[str, Any] | None = None) -> int:
        """Execute an UPDATE/INSERT."""
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

    def read_schemas(self) -> list[str]:
        """List schemas (SQLite has only 'main')."""
        return ["main"]

    def read_tables(self, schema: str) -> list[str]:
        """List tables in the database."""
        conn = self._require_connection()
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
        return [row["name"] for row in cursor.fetchall()]

    def read_columns(
        self,
        schema: str,
        table: str,
        filter_pattern: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return column metadata for a table."""
        conn = self._require_connection()
        cursor = conn.execute(f"PRAGMA table_info({table})")  # noqa: S608
        columns: list[dict[str, Any]] = []
        for row in cursor.fetchall():
            col: dict[str, Any] = {
                "name": row["name"],
                "type": row["type"],
                "nullable": not bool(row["notnull"]),
                "default": row["dflt_value"],
                "is_primary_key": row["pk"] > 0,
            }
            columns.append(col)
        if filter_pattern is not None:
            columns = [
                c for c in columns if fnmatch(c["name"].lower(), filter_pattern.lower())
            ]
        return columns

    def read_relations(self, schema: str, table: str) -> list[dict[str, Any]]:
        """Return foreign-key relationships."""
        conn = self._require_connection()
        cursor = conn.execute(f"PRAGMA foreign_key_list({table})")  # noqa: S608
        relations: list[dict[str, Any]] = []
        for row in cursor.fetchall():
            rel: dict[str, Any] = {
                "constraint_name": f"fk_{row['id']}",
                "column": row["from"],
                "referenced_table": row["table"],
                "referenced_column": row["to"],
                "on_update": row["on_update"],
                "on_delete": row["on_delete"],
            }
            relations.append(rel)
        return relations
