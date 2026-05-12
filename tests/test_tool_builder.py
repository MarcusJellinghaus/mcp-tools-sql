"""Tests for tool_builder helper functions."""

from __future__ import annotations

import asyncio
import inspect
from pathlib import Path

from mcp_tools_sql.backends.sqlite import SQLiteBackend
from mcp_tools_sql.config.models import (
    BackendQueryConfig,
    ConnectionConfig,
    QueryConfig,
    QueryParamConfig,
)
from mcp_tools_sql.tool_builder import apply_filter, build_tool_fn, extract_sql_params


class TestExtractSqlParams:
    """Tests for extract_sql_params."""

    def test_single_param(self) -> None:
        assert extract_sql_params("SELECT * WHERE x = :id") == {"id"}

    def test_multiple_params(self) -> None:
        assert extract_sql_params("WHERE a = :x AND b = :y") == {"x", "y"}

    def test_no_params(self) -> None:
        assert extract_sql_params("SELECT 'main' AS name") == set()

    def test_duplicate_param(self) -> None:
        assert extract_sql_params("WHERE a = :x OR b = :x") == {"x"}


class TestApplyFilter:
    """Tests for apply_filter."""

    def test_no_filter(self) -> None:
        """None filter returns all rows."""
        rows = [{"name": "a"}, {"name": "b"}]
        assert apply_filter(rows, "name", None) == rows

    def test_glob_match(self) -> None:
        """Glob pattern filters rows by the given column."""
        rows = [
            {"name": "user_id"},
            {"name": "user_name"},
            {"name": "order_id"},
        ]
        result = apply_filter(rows, "name", "user_*")
        assert result == [{"name": "user_id"}, {"name": "user_name"}]

    def test_case_insensitive(self) -> None:
        """Filter is case-insensitive."""
        rows = [{"name": "User_ID"}, {"name": "order_id"}]
        result = apply_filter(rows, "name", "user_*")
        assert result == [{"name": "User_ID"}]

    def test_no_match(self) -> None:
        """No matching rows returns empty list."""
        rows = [{"name": "a"}, {"name": "b"}]
        assert apply_filter(rows, "name", "z*") == []

    def test_apply_filter_column_absent_from_rows_returns_empty(self) -> None:
        """A filter_column missing from row keys yields empty list (no KeyError)."""
        rows = [{"other": "a"}, {"other": "b"}]
        assert apply_filter(rows, "missing", "a*") == []


def _stub_backend() -> SQLiteBackend:
    """Return an unconnected SQLite backend stub for signature-only checks."""
    return SQLiteBackend(ConnectionConfig(backend="sqlite", path=":memory:"))


class TestBuildFnImplicitParams:
    """Tests for max_rows / <col>_filter auto-injection in built signatures."""

    def test_build_fn_injects_max_rows(self) -> None:
        """Built signature always contains a max_rows param with the configured default."""
        config = QueryConfig(
            sql="SELECT * FROM t WHERE x = :x",
            params={"x": QueryParamConfig(name="x", type="str")},
            max_rows_default=42,
        )
        fn = build_tool_fn("t1", config, _stub_backend(), "sqlite")
        sig = inspect.signature(fn)
        assert "max_rows" in sig.parameters
        assert sig.parameters["max_rows"].default == 42

    def test_build_fn_injects_filter_when_set(self) -> None:
        """filter_column='name' yields a name_filter param defaulting to None."""
        config = QueryConfig(
            sql="SELECT name FROM t",
            filter_column="name",
        )
        fn = build_tool_fn("t2", config, _stub_backend(), "sqlite")
        sig = inspect.signature(fn)
        assert "name_filter" in sig.parameters
        assert sig.parameters["name_filter"].default is None

    def test_build_fn_no_filter_when_unset(self) -> None:
        """Empty filter_column yields no implicit *_filter parameter."""
        config = QueryConfig(sql="SELECT 1 AS x")
        fn = build_tool_fn("t3", config, _stub_backend(), "sqlite")
        sig = inspect.signature(fn)
        assert not any(p.endswith("_filter") for p in sig.parameters)

    def test_build_fn_filter_uses_custom_column_prefix(self) -> None:
        """filter_column='family_name' yields a family_name_filter param."""
        config = QueryConfig(
            sql="SELECT family_name FROM t",
            filter_column="family_name",
        )
        fn = build_tool_fn("t4", config, _stub_backend(), "sqlite")
        sig = inspect.signature(fn)
        assert "family_name_filter" in sig.parameters

    def test_build_fn_does_not_declare_user_filter_or_max_rows(self) -> None:
        """Only user-declared params + injected max_rows (+ optional *_filter) appear."""
        config = QueryConfig(
            sql="SELECT name FROM t WHERE schema = :schema",
            params={"schema": QueryParamConfig(name="schema", type="str")},
            filter_column="name",
        )
        fn = build_tool_fn("t5", config, _stub_backend(), "sqlite")
        sig = inspect.signature(fn)
        assert set(sig.parameters) == {"schema", "max_rows", "name_filter"}


class TestBuildFnFilterBehavior:
    """End-to-end behavior of filter_column applied at runtime."""

    def test_apply_filter_uses_config_filter_column(self) -> None:
        """When filter_column is set, apply_filter targets that exact column."""
        rows = [
            {"family_name": "Adams"},
            {"family_name": "Brown"},
            {"family_name": "Andrews"},
        ]
        assert apply_filter(rows, "family_name", "a*") == [
            {"family_name": "Adams"},
            {"family_name": "Andrews"},
        ]


def test_build_fn_runtime_uses_name_filter_kwarg(sqlite_db: Path) -> None:
    """Calling the built fn with ``name_filter`` actually filters rows."""
    backend = SQLiteBackend(ConnectionConfig(backend="sqlite", path=str(sqlite_db)))
    backend.connect()
    config = QueryConfig(
        sql="SELECT name FROM pragma_table_info(:table)",
        params={"table": QueryParamConfig(name="table", type="str")},
        backends={
            "sqlite": BackendQueryConfig(
                sql="SELECT name FROM pragma_table_info(:table)"
            )
        },
        filter_column="name",
    )
    fn = build_tool_fn("t_filter", config, backend, "sqlite")
    try:
        text = asyncio.run(fn(table="customers", name_filter="na*"))
        assert "name" in text
        assert "country" not in text
    finally:
        backend.close()
