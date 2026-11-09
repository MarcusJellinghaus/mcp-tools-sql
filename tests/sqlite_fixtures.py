"""SQLite fixture helpers for tests outside tests/backends/.

The only non-owner test module allowed to import sqlite3 (see the
sqlite3_isolation contract in .importlinter). Other tests build and inspect
fixture databases through these helpers, never through sqlite3 directly.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


def create_db(path: Path, script: str = "") -> Path:
    """Create (or open) the database file and run *script* via executescript.

    Args:
        path: Database file to create or open.
        script: SQL script to run; empty creates the file only.

    Returns:
        *path*, for chaining.
    """
    conn = sqlite3.connect(str(path))
    try:
        conn.executescript(script)
        conn.commit()
    finally:
        conn.close()
    return path


def query(
    path: Path,
    sql: str,
    params: Sequence[Any] | Mapping[str, Any] = (),
) -> list[tuple[Any, ...]]:
    """Run one statement on a fresh connection and commit.

    Args:
        path: Database file.
        sql: Single statement with ``?`` or ``:name`` placeholders.
        params: Positional or named parameters.

    Returns:
        All result rows as tuples (empty for writes).
    """
    conn = sqlite3.connect(str(path))
    try:
        rows = conn.execute(sql, params).fetchall()
        conn.commit()
        return [tuple(row) for row in rows]
    finally:
        conn.close()
