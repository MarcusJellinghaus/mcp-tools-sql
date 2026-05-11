"""Tests for default_queries.toml loading and SQLite pragma binding."""

import sqlite3
from pathlib import Path

from mcp_tools_sql.schema_tools import load_default_queries

EXPECTED_NAMES = {"read_schemas", "read_tables", "read_columns", "read_relations"}


class TestDefaultQueriesLoading:
    """Tests for loading and validating the default queries TOML."""

    def test_loads_four_queries(self) -> None:
        """load_default_queries() returns exactly 4 entries."""
        queries = load_default_queries()
        assert len(queries) == 4

    def test_query_names(self) -> None:
        """Expected keys: read_schemas, read_tables, read_columns, read_relations."""
        queries = load_default_queries()
        assert set(queries.keys()) == EXPECTED_NAMES

    def test_sqlite_overrides_present(self) -> None:
        """Each query has a backends.sqlite entry."""
        queries = load_default_queries()
        for name, config in queries.items():
            assert "sqlite" in config.backends, f"{name} missing sqlite override"

    def test_resolve_sql_sqlite(self) -> None:
        """resolve_sql('sqlite') returns SQLite-specific SQL for each query."""
        queries = load_default_queries()
        for name, config in queries.items():
            resolved = config.resolve_sql("sqlite")
            assert (
                resolved == config.backends["sqlite"].sql
            ), f"{name}: resolve_sql('sqlite') should return the override"
            assert (
                resolved != config.sql
            ), f"{name}: sqlite SQL should differ from default"

    def test_read_columns_filter_column_is_name(self) -> None:
        """read_columns sets filter_column = 'name' for implicit name_filter."""
        queries = load_default_queries()
        columns_config = queries["read_columns"]
        assert columns_config.filter_column == "name"

    def test_read_columns_has_only_schema_and_table_params(self) -> None:
        """read_columns user-declared params are exactly {schema, table}."""
        queries = load_default_queries()
        columns_config = queries["read_columns"]
        assert set(columns_config.params.keys()) == {"schema", "table"}


class TestSqlitePragmaBinding:
    """Verify SQLite pragma function-form works with named param binding."""

    def test_pragma_table_info_named_param(self, sqlite_db: Path) -> None:
        """Verify pragma_table_info(:table) works with named param binding."""
        conn = sqlite3.connect(str(sqlite_db))
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.execute(
                'SELECT name, type, "notnull", dflt_value, pk '
                "FROM pragma_table_info(:table)",
                {"table": "customers"},
            )
            rows = cursor.fetchall()
            col_names = [row["name"] for row in rows]
            assert "id" in col_names
            assert "name" in col_names
            assert "country" in col_names
        finally:
            conn.close()

    def test_pragma_foreign_key_list_named_param(self, sqlite_db: Path) -> None:
        """Verify pragma_foreign_key_list(:table) works with named param binding."""
        conn = sqlite3.connect(str(sqlite_db))
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.execute(
                'SELECT id, "from", "table", "to" '
                "FROM pragma_foreign_key_list(:table)",
                {"table": "orders"},
            )
            rows = cursor.fetchall()
            assert len(rows) >= 1
            row = rows[0]
            assert row["table"] == "customers"
        finally:
            conn.close()
