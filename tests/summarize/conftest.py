"""Fixtures for the ``summarize_columns`` end-to-end tests.

``profiling_db`` seeds a SQLite database whose ``profile_me`` table exercises
every profiling category and edge case the deep view must handle: an integer
column carrying a zero and a negative, a text column with duplicates plus a
NULL plus a whitespace-only value (empty-after-trim), a unique-key text column
(the sample-values path), a date (temporal) column, a boolean column mixing
true/false and a NULL, and an all-NULL column (the ``value_kind == "none"``
short-circuit). It also seeds an empty table (zero-row message) and a wide
table (> 15 columns → triage).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Generator
from pathlib import Path

import pytest


@pytest.fixture
def profiling_db(tmp_path: Path) -> Generator[Path, None, None]:
    """Create a SQLite database seeded for column-profiling tests.

    Yields:
        The path to the seeded SQLite database file.
    """
    db_path = tmp_path / "profiling.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE profile_me ("
        "qty INTEGER, category TEXT, ref TEXT, created DATE, "
        "is_active BOOLEAN, note TEXT)"
    )
    rows = [
        (10, "x", "R1", "2020-01-01", 1, None),
        (0, "x", "R2", "2020-06-15", 0, None),
        (-5, "y", "R3", "2021-03-20", 1, None),
        (20, "y", "R4", "2022-11-11", None, None),
        (7, None, "R5", "2023-07-04", 0, None),
        (3, "   ", "R6", "2024-02-29", 1, None),
    ]
    conn.executemany(
        "INSERT INTO profile_me "
        "(qty, category, ref, created, is_active, note) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        rows,
    )

    conn.execute("CREATE TABLE empty_t (a INTEGER, b TEXT)")

    wide_cols = ", ".join(f"w{i} INTEGER" for i in range(20))
    conn.execute(f"CREATE TABLE wide_t ({wide_cols})")  # noqa: S608
    placeholders = ", ".join("?" for _ in range(20))
    conn.execute(
        f"INSERT INTO wide_t VALUES ({placeholders})",  # noqa: S608
        tuple(range(20)),
    )

    conn.commit()
    conn.close()
    yield db_path
