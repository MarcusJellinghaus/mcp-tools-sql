"""SQLite database backend."""

from __future__ import annotations

import sqlite3
import threading
import time
from collections.abc import Generator, Iterator
from contextlib import contextmanager
from typing import Any

from mcp_tools_sql.backends.base import (
    FETCH_BATCH_SIZE,
    DatabaseBackend,
    Deadline,
    QueryTimeoutError,
    translate_timeout,
    wrap_driver_error,
)
from mcp_tools_sql.config.models import ConnectionConfig

_PROGRESS_STEPS = 1000  # VM instructions between deadline checks

_CONNECTION_ERRORS: tuple[type[sqlite3.Error], ...] = (
    sqlite3.OperationalError,
    sqlite3.InterfaceError,
)


@contextmanager
def _driver_errors() -> Iterator[None]:
    """Translate sqlite3.Error into BackendError / BackendConnectionError.

    ``OperationalError`` and ``InterfaceError`` become
    :class:`BackendConnectionError`, every other ``sqlite3.Error`` a plain
    :class:`BackendError`. Non-driver exceptions pass through unchanged.
    """
    try:
        yield
    except sqlite3.Error as exc:
        neutral = wrap_driver_error(exc, _CONNECTION_ERRORS)
        raise neutral from exc


@contextmanager
def _statement_deadline(
    conn: sqlite3.Connection, seconds: int, counting: Deadline | None = None
) -> Iterator[None]:
    """Interrupt statements on *conn* that run past the deadline.

    Installs a progress handler for the duration of the block and removes it
    in ``finally``, so the connection is clean afterwards. The handler fires
    at the earlier of ``seconds`` from entry and ``counting.at`` (when armed);
    the statement deadline is never extended.

    Args:
        conn: The connection the wrapped statements run on.
        seconds: Statement timeout in seconds.
        counting: Optional caller-set counting deadline.

    Raises:
        QueryTimeoutError: When a statement was interrupted.
        sqlite3.Error: Any other driver error, re-raised unchanged.
    """
    stop = time.monotonic() + seconds

    def _handler() -> int:
        limit = stop
        if counting is not None and counting.at is not None:
            limit = min(stop, counting.at)
        return int(time.monotonic() >= limit)

    conn.set_progress_handler(_handler, _PROGRESS_STEPS)
    try:
        yield
    except sqlite3.Error as exc:
        if translate_timeout(exc, seconds) is not None:
            raise QueryTimeoutError(seconds) from exc
        raise
    finally:
        conn.set_progress_handler(None, 0)


class SQLiteBackend(DatabaseBackend):
    """Backend for SQLite databases.

    Every public driver-touching method raises ``sqlite3`` errors as
    :class:`BackendError` (via :func:`_driver_errors`); statement timeouts are
    translated first and raise :class:`QueryTimeoutError`.
    """

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
        with _driver_errors(), self._connect_lock:
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
        with _driver_errors():
            if self._connection is not None:
                self._connection.close()
                self._connection = None
            self._closed = True

    def _require_connection(self) -> sqlite3.Connection:
        """Lazily connect and return the live connection.

        Returns:
            The open SQLite connection.

        Raises:
            RuntimeError: If no connection is open after ``connect()``.
        """
        self.connect()
        if self._connection is None:
            msg = "Backend connection is not open."
            raise RuntimeError(msg)
        return self._connection

    def execute_query(
        self, sql: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Execute a SELECT query under the statement timeout.

        Raises :class:`QueryTimeoutError` (from :func:`_statement_deadline`)
        if execute + fetch exceed ``query_timeout_seconds``.

        Returns:
            Rows as a list of dicts.
        """
        with _driver_errors():
            conn = self._require_connection()
            with _statement_deadline(conn, self._config.query_timeout_seconds):
                cursor = conn.execute(sql, params or {})
                return [dict(row) for row in cursor.fetchall()]

    def execute_readonly_query(
        self, sql: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Execute a SELECT on a fresh ``PRAGMA query_only = ON`` connection.

        Opens a brand-new single-use connection to the same database file,
        sets ``query_only`` so the DB rejects any write, runs the query, and
        closes the connection in ``finally``. The persistent connection is
        never touched. Execute + fetch run under the statement timeout and
        raise :class:`QueryTimeoutError` if they exceed
        ``query_timeout_seconds``.

        Returns:
            Rows as a list of dicts.

        Raises:
            ValueError: If the connection path is empty.
        """
        with _driver_errors():
            path = self._config.path
            if not path:
                msg = "SQLite path must not be empty."
                raise ValueError(msg)
            conn = sqlite3.connect(path, check_same_thread=False)
            try:
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA query_only = ON")
                with _statement_deadline(conn, self._config.query_timeout_seconds):
                    cursor = conn.execute(sql, params or {})
                    return [dict(row) for row in cursor.fetchall()]
            finally:
                conn.close()

    def iter_readonly_batches(
        self,
        sql: str,
        params: dict[str, Any] | None = None,
        *,
        counting: Deadline | None = None,
    ) -> Generator[list[dict[str, Any]], None, None]:
        """Yield rows in batches from a fresh ``PRAGMA query_only = ON`` connection.

        Same read-only guarantee and fresh-connection lifecycle as
        :meth:`execute_readonly_query`. Execute and the whole fetch loop run
        under the statement timeout and the optional *counting* deadline. The
        cursor and connection are closed in ``finally``, so closing the
        generator early releases both. A :class:`QueryTimeoutError` is raised
        if the statement timeout or the counting deadline interrupted execute
        or fetch; never continue fetching after one.

        Args:
            sql: The SELECT statement to execute.
            params: Optional values for ``:name`` placeholders in *sql*.
            counting: Optional caller-set counting deadline.

        Yields:
            Non-empty lists of row dicts, each at most ``FETCH_BATCH_SIZE``
            long.

        Raises:
            ValueError: If the connection path is empty.
        """
        with _driver_errors():
            path = self._config.path
            if not path:
                msg = "SQLite path must not be empty."
                raise ValueError(msg)
            conn = sqlite3.connect(path, check_same_thread=False)
            cursor: sqlite3.Cursor | None = None
            try:
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA query_only = ON")
                with _statement_deadline(
                    conn, self._config.query_timeout_seconds, counting
                ):
                    cursor = conn.execute(sql, params or {})
                    while batch := cursor.fetchmany(FETCH_BATCH_SIZE):
                        yield [dict(row) for row in batch]
            finally:
                if cursor is not None:
                    cursor.close()
                conn.close()

    def execute_readonly_query_with_columns(
        self, sql: str, params: dict[str, Any] | None = None
    ) -> tuple[list[str], list[tuple[Any, ...]]]:
        """Execute a SELECT on a fresh ``PRAGMA query_only = ON`` connection.

        Same read-only guarantee and lifecycle as
        :meth:`execute_readonly_query` — a brand-new single-use connection to
        the same database file, ``query_only`` set so the DB rejects any
        write, closed in ``finally``, persistent connection never touched.
        Only the result shape differs: ordered column names plus positional
        row tuples, so duplicate column names survive. Execute + fetch run
        under the statement timeout and raise :class:`QueryTimeoutError` if
        they exceed ``query_timeout_seconds``.

        Args:
            sql: The SELECT statement to execute.
            params: Optional values for ``:name`` placeholders in *sql*.

        Returns:
            Tuple ``(columns, rows)``: column names in projection order, and
            one plain tuple per row positionally aligned with *columns*.

        Raises:
            ValueError: If the connection path is empty.
        """
        with _driver_errors():
            path = self._config.path
            if not path:
                msg = "SQLite path must not be empty."
                raise ValueError(msg)
            conn = sqlite3.connect(path, check_same_thread=False)
            try:
                conn.execute("PRAGMA query_only = ON")
                with _statement_deadline(conn, self._config.query_timeout_seconds):
                    cursor = conn.execute(sql, params or {})
                    columns = [d[0] for d in cursor.description or ()]
                    return columns, [tuple(row) for row in cursor.fetchall()]
            finally:
                conn.close()

    def execute_update(self, sql: str, params: dict[str, Any] | None = None) -> int:
        """Execute an UPDATE/INSERT under the statement timeout.

        Raises :class:`QueryTimeoutError` (from :func:`_statement_deadline`)
        if execute + commit exceed ``query_timeout_seconds``.

        Returns:
            Number of affected rows.
        """
        with _driver_errors():
            conn = self._require_connection()
            with _statement_deadline(conn, self._config.query_timeout_seconds):
                cursor = conn.execute(sql, params or {})
                conn.commit()
                return cursor.rowcount

    def explain(self, sql: str, params: dict[str, Any] | None = None) -> str:
        """Return the query execution plan under the statement timeout.

        SQLite's ``EXPLAIN QUERY PLAN`` requires bound values to compile
        parameterized SQL, so callers must pass ``params`` whenever the SQL
        references ``:name`` placeholders. Raises :class:`QueryTimeoutError`
        (from :func:`_statement_deadline`) if execute + fetch exceed
        ``query_timeout_seconds``.
        """
        with _driver_errors():
            conn = self._require_connection()
            with _statement_deadline(conn, self._config.query_timeout_seconds):
                cursor = conn.execute(f"EXPLAIN QUERY PLAN {sql}", params or {})
                rows = cursor.fetchall()
            return "\n".join(row["detail"] for row in rows)

    @contextmanager
    def get_isolated_connection(self) -> Iterator[Any]:
        """Yield the persistent connection (no-op isolation for SQLite).

        ``EXPLAIN QUERY PLAN`` does not execute the statement, so reusing the
        persistent connection is safe. Callers MUST NOT close the yielded
        connection.
        """
        yield self._require_connection()
