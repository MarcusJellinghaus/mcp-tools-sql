"""Shared test fixtures."""

from __future__ import annotations

import os
import uuid
from collections.abc import Generator
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

import pytest

from mcp_tools_sql.config.models import ConnectionConfig
from tests.sqlite_fixtures import create_db, query


@pytest.fixture
def sqlite_db(tmp_path: Path) -> Generator[Path, None, None]:
    """Create a SQLite database with test schema and seed data."""
    yield create_db(
        tmp_path / "test.db",
        """
        CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT, country TEXT);
        CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id INTEGER REFERENCES customers(id), status TEXT, total REAL);
        INSERT INTO customers VALUES (1, 'Bank A', 'Germany');
        INSERT INTO customers VALUES (2, 'Bank B', 'France');
        INSERT INTO orders VALUES (1, 1, 'pending', 1000.0);
        INSERT INTO orders VALUES (2, 1, 'shipped', 2500.0);
        INSERT INTO orders VALUES (3, 2, 'pending', 750.0);
        """,
    )


@pytest.fixture
def sqlite_wide_db(tmp_path: Path) -> Generator[Path, None, None]:
    """Create a SQLite database with a wide table (150 columns) for truncation tests."""
    db_path = create_db(tmp_path / "wide.db")
    columns = ", ".join(f"col_{i} TEXT" for i in range(150))
    query(db_path, f"CREATE TABLE wide_table ({columns})")
    placeholders = ", ".join("?" for _ in range(150))
    values = tuple(f"val_{i}" for i in range(150))
    query(db_path, f"INSERT INTO wide_table VALUES ({placeholders})", values)
    yield db_path


@dataclass
class MSSQLTestEnv:
    """Environment for MSSQL integration tests."""

    config: ConnectionConfig
    schema: str


_MSSQL_REQUIRED_VARS = (
    "TEST_MSSQL_HOST",
    "TEST_MSSQL_PORT",
    "TEST_MSSQL_USER",
    "TEST_MSSQL_PASSWORD",
)


@pytest.fixture
def mssql_db() -> Generator[MSSQLTestEnv, None, None]:
    """Provision a unique schema with seed data on a real SQL Server.

    Skips when ``TEST_MSSQL_*`` env vars are not set. Yields the connection
    config and schema name; tears down the schema and tables afterwards.
    """
    missing = [v for v in _MSSQL_REQUIRED_VARS if not os.environ.get(v)]
    if missing:
        pytest.skip(f"TEST_MSSQL_* not set: {', '.join(missing)}")

    from mcp_tools_sql.backends.mssql import (  # pylint: disable=import-outside-toplevel
        MSSQLBackend,
    )

    cfg = ConnectionConfig(
        backend="mssql",
        host=os.environ["TEST_MSSQL_HOST"],
        port=int(os.environ["TEST_MSSQL_PORT"]),
        database=os.environ.get("TEST_MSSQL_DB", "master"),
        username=os.environ["TEST_MSSQL_USER"],
        password=os.environ["TEST_MSSQL_PASSWORD"],
        encrypt=True,
        trust_server_certificate=True,
    )
    schema = f"test_{uuid.uuid4().hex[:8]}"

    with MSSQLBackend(cfg) as setup_backend:
        setup_backend.execute_update(f"CREATE SCHEMA {schema}")
        setup_backend.execute_update(
            f"CREATE TABLE {schema}.customers "
            "(id INT PRIMARY KEY, name NVARCHAR(50), country NVARCHAR(50))"
        )
        setup_backend.execute_update(
            f"CREATE TABLE {schema}.orders "
            "(id INT PRIMARY KEY, customer_id INT, "
            "status NVARCHAR(20), total FLOAT)"
        )
        for cid, name, country in (
            (1, "Bank A", "Germany"),
            (2, "Bank B", "France"),
        ):
            setup_backend.execute_update(
                f"INSERT INTO {schema}.customers (id, name, country) "
                "VALUES (:id, :name, :country)",
                {"id": cid, "name": name, "country": country},
            )
        for oid, customer_id, status, total in (
            (1, 1, "pending", 1000.0),
            (2, 1, "shipped", 2500.0),
            (3, 2, "pending", 750.0),
        ):
            setup_backend.execute_update(
                f"INSERT INTO {schema}.orders (id, customer_id, status, total) "
                "VALUES (:id, :customer_id, :status, :total)",
                {
                    "id": oid,
                    "customer_id": customer_id,
                    "status": status,
                    "total": total,
                },
            )

    env = MSSQLTestEnv(config=cfg, schema=schema)
    try:
        yield env
    finally:
        with MSSQLBackend(cfg) as teardown_backend:
            with suppress(Exception):
                teardown_backend.execute_update(f"DROP TABLE {schema}.orders")
            with suppress(Exception):
                teardown_backend.execute_update(f"DROP TABLE {schema}.customers")
            with suppress(Exception):
                teardown_backend.execute_update(f"DROP SCHEMA {schema}")
