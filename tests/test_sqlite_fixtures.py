"""Tests for the tests/sqlite_fixtures.py helpers."""

from __future__ import annotations

from pathlib import Path

from tests.sqlite_fixtures import create_db, query


def test_create_then_query_round_trip(tmp_path: Path) -> None:
    """A table created by create_db is readable through query."""
    db = create_db(
        tmp_path / "t.db",
        "CREATE TABLE t (id INTEGER, name TEXT);"
        "INSERT INTO t VALUES (1, 'a'), (2, 'b');",
    )
    assert db == tmp_path / "t.db"
    assert query(db, "SELECT id, name FROM t ORDER BY id") == [(1, "a"), (2, "b")]


def test_query_named_params_and_commit(tmp_path: Path) -> None:
    """Named params bind, and writes made through query are committed."""
    db = create_db(tmp_path / "t.db", "CREATE TABLE t (id INTEGER, name TEXT);")
    assert query(db, "INSERT INTO t VALUES (:id, :name)", {"id": 7, "name": "x"}) == []
    assert query(db, "SELECT name FROM t WHERE id = :id", {"id": 7}) == [("x",)]
