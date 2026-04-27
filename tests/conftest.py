"""Shared test fixtures."""

import sqlite3
from collections.abc import Generator
from pathlib import Path

import pytest


@pytest.fixture
def sqlite_db(tmp_path: Path) -> Generator[Path, None, None]:
    """Create a SQLite database with test schema and seed data."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT, country TEXT)"
    )
    conn.execute(
        "CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id INTEGER REFERENCES customers(id), status TEXT, total REAL)"
    )
    conn.execute("INSERT INTO customers VALUES (1, 'Bank A', 'Germany')")
    conn.execute("INSERT INTO customers VALUES (2, 'Bank B', 'France')")
    conn.execute("INSERT INTO orders VALUES (1, 1, 'pending', 1000.0)")
    conn.execute("INSERT INTO orders VALUES (2, 1, 'shipped', 2500.0)")
    conn.execute("INSERT INTO orders VALUES (3, 2, 'pending', 750.0)")
    conn.commit()
    conn.close()
    yield db_path


@pytest.fixture
def sqlite_wide_db(tmp_path: Path) -> Generator[Path, None, None]:
    """Create a SQLite database with a wide table (150 columns) for truncation tests."""
    db_path = tmp_path / "wide.db"
    conn = sqlite3.connect(str(db_path))
    columns = ", ".join(f"col_{i} TEXT" for i in range(150))
    conn.execute(f"CREATE TABLE wide_table ({columns})")  # noqa: S608
    placeholders = ", ".join("?" for _ in range(150))
    values = tuple(f"val_{i}" for i in range(150))
    conn.execute(
        f"INSERT INTO wide_table VALUES ({placeholders})", values
    )  # noqa: S608
    conn.commit()
    conn.close()
    yield db_path


@pytest.fixture
def sqlite_memory_db() -> Generator[sqlite3.Connection, None, None]:
    """Create an in-memory SQLite database with test data."""
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT, country TEXT)"
    )
    conn.execute(
        "CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id INTEGER REFERENCES customers(id), status TEXT, total REAL)"
    )
    conn.execute("INSERT INTO customers VALUES (1, 'Bank A', 'Germany')")
    conn.execute("INSERT INTO customers VALUES (2, 'Bank B', 'France')")
    conn.execute("INSERT INTO orders VALUES (1, 1, 'pending', 1000.0)")
    conn.execute("INSERT INTO orders VALUES (2, 1, 'shipped', 2500.0)")
    conn.execute("INSERT INTO orders VALUES (3, 2, 'pending', 750.0)")
    conn.commit()
    yield conn
    conn.close()
