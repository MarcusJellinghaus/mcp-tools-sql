"""Tests for :mod:`mcp_tools_sql.toolset`."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from mcp_tools_sql.backends.registry import BackendRegistry
from mcp_tools_sql.toolset import SqlToolset, build_toolset
from mcp_tools_sql.utils.tool_spec import ToolSpec
from tests.sqlite_fixtures import create_db

_QUERIES = (
    "\n[queries.foo]\n"
    'description = "Foo query"\n'
    'sql = "SELECT * FROM customers"\n'
    "\n[queries.by_name]\n"
    'description = "Customers by optional name"\n'
    'sql = "SELECT * FROM customers WHERE name = COALESCE(:name, name)"\n'
    "\n[queries.by_name.params.name]\n"
    'name = "name"\n'
    'type = "str"\n'
    "required = false\n"
)

_UPDATES = (
    "\n[updates.set_name]\n"
    'description = "Set customer name"\n'
    'table = "customers"\n'
    "\n[updates.set_name.key]\n"
    'field = "id"\n'
    'type = "int"\n'
    "\n[[updates.set_name.fields]]\n"
    'field = "name"\n'
    'type = "str"\n'
    "required = true\n"
)


def _make_db(path: Path) -> None:
    create_db(
        path,
        "CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT);"
        "INSERT INTO customers VALUES (1, 'Alice');",
    )


def _write_configs(
    tmp_path: Path,
    *,
    queries: str = _QUERIES,
    updates: str = _UPDATES,
    allow_updates: bool = True,
    multi: bool = False,
    extra_connections: str = "",
) -> tuple[Path, Path]:
    """Write SQLite query + database configs and return their paths.

    ``extra_connections`` is TOML appended after the sqlite connections.
    """
    db_a = tmp_path / "a.db"
    _make_db(db_a)
    qcfg = tmp_path / "mcp-tools-sql.toml"
    qcfg.write_text('connection = "default"\n' + queries + updates, encoding="utf-8")
    text = f'[connections.default]\nbackend = "sqlite"\npath = "{db_a.as_posix()}"\n'
    if multi:
        db_b = tmp_path / "b.db"
        _make_db(db_b)
        text += (
            f'\n[connections.second]\nbackend = "sqlite"\npath = "{db_b.as_posix()}"\n'
        )
    text += extra_connections
    text += f"\n[security]\nallow_updates = {str(allow_updates).lower()}\n"
    dbcfg = tmp_path / "db.toml"
    dbcfg.write_text(text, encoding="utf-8")
    return qcfg, dbcfg


def _by_name(toolset: SqlToolset) -> dict[str, ToolSpec]:
    return {spec.name: spec for spec in toolset.specs}


async def _call(spec: ToolSpec, kwargs: dict[str, Any]) -> Any:
    """Validate ``kwargs`` through ``args_model`` and call the tool."""
    validated = spec.args_model.model_validate(kwargs)
    return await spec.fn(
        **{f: getattr(validated, f) for f in spec.args_model.model_fields}
    )


def _counting_close_all(
    monkeypatch: pytest.MonkeyPatch,
) -> list[BackendRegistry]:
    """Patch ``BackendRegistry.close_all`` to record each registry it closes."""
    closed: list[BackendRegistry] = []
    original = BackendRegistry.close_all

    def counting(self: BackendRegistry) -> None:
        closed.append(self)
        original(self)

    monkeypatch.setattr(BackendRegistry, "close_all", counting)
    return closed


_EXPECTED_SINGLE = {
    "read_schemas": ("sql.schema", True),
    "read_tables": ("sql.schema", True),
    "read_columns": ("sql.schema", True),
    "read_relations": ("sql.schema", True),
    "validate_sql": ("sql.validation", True),
    "verify": ("sql.validation", True),
    "count_records": ("sql.profiling", True),
    "summarize_columns": ("sql.profiling", True),
    "query_foo": ("sql.query", True),
    "query_by_name": ("sql.query", True),
    "update_set_name": ("sql.update", False),
}


def test_groups_and_read_only_single_target(tmp_path: Path) -> None:
    with build_toolset(*_write_configs(tmp_path)) as toolset:
        actual = {s.name: (s.group, s.read_only) for s in toolset.specs}
    assert actual == _EXPECTED_SINGLE


def test_groups_and_read_only_multi_target(tmp_path: Path) -> None:
    with build_toolset(*_write_configs(tmp_path, multi=True)) as toolset:
        actual = {s.name: (s.group, s.read_only) for s in toolset.specs}
    assert actual == {**_EXPECTED_SINGLE, "read_databases": ("sql.schema", True)}


def test_tool_order_matches_server(tmp_path: Path) -> None:
    with build_toolset(*_write_configs(tmp_path, multi=True)) as toolset:
        names = [s.name for s in toolset.specs]
    assert names.index("summarize_columns") < names.index("read_databases")
    assert names.index("read_databases") < names.index("verify")
    assert names.index("verify") < names.index("query_foo")
    assert names.index("query_by_name") < names.index("update_set_name")


def test_updates_hidden_without_allow_updates(tmp_path: Path) -> None:
    with build_toolset(*_write_configs(tmp_path, allow_updates=False)) as toolset:
        names = {s.name for s in toolset.specs}
    assert "update_set_name" not in names
    assert "read_databases" not in names


def test_public_attributes(tmp_path: Path) -> None:
    with build_toolset(*_write_configs(tmp_path)) as toolset:
        assert toolset.query_config.connection == "default"
        assert toolset.targets.default.connection == "default"


def test_max_rows_below_minimum_rejected(tmp_path: Path) -> None:
    with build_toolset(*_write_configs(tmp_path)) as toolset:
        spec = _by_name(toolset)["query_foo"]
        with pytest.raises(ValidationError):
            spec.args_model.model_validate({"max_rows": 0})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("name", "kwargs", "multi"),
    [
        pytest.param("read_tables", {"schema": "main"}, False, id="schema"),
        pytest.param("validate_sql", {"sql": "SELECT 1"}, False, id="validate_sql"),
        pytest.param(
            "count_records",
            {"sql": "SELECT * FROM customers"},
            False,
            id="count_records",
        ),
        pytest.param("summarize_columns", {}, False, id="summarize_columns"),
        pytest.param("query_by_name", {}, False, id="query-optional-param"),
        pytest.param("update_set_name", {"id": 1, "name": "Bob"}, False, id="update"),
        pytest.param("verify", {}, False, id="verify"),
        pytest.param("read_databases", {}, True, id="read_databases"),
    ],
)
async def test_each_tool_callable_with_required_args_only(
    tmp_path: Path, name: str, kwargs: dict[str, Any], multi: bool
) -> None:
    with build_toolset(*_write_configs(tmp_path, multi=multi)) as toolset:
        result = await _call(_by_name(toolset)[name], kwargs)
    assert isinstance(result, str)


@pytest.mark.asyncio
async def test_query_optional_param_omitted_returns_rows(tmp_path: Path) -> None:
    with build_toolset(*_write_configs(tmp_path)) as toolset:
        result = await _call(_by_name(toolset)["query_by_name"], {})
    assert "Alice" in result


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("name", "kwargs"),
    [
        pytest.param(
            "summarize_columns",
            {"schema": "main", "table": "customers"},
            id="summarize_columns",
        ),
        pytest.param(
            "read_columns",
            {"schema": "main", "table": "customers"},
            id="read_columns",
        ),
    ],
)
async def test_schema_param_survives_args_model(
    tmp_path: Path, name: str, kwargs: dict[str, Any]
) -> None:
    """A ``schema`` field shadows ``BaseModel.schema`` but still validates."""
    with build_toolset(*_write_configs(tmp_path)) as toolset:
        spec = _by_name(toolset)[name]
        assert "schema" in spec.args_model.model_json_schema()["properties"]
        validated = spec.args_model.model_validate(kwargs)
        # Plain `.schema` types as BaseModel.schema to mypy; getattr is the point.
        assert getattr(validated, "schema") == "main"  # noqa: B009
        result = await _call(spec, kwargs)
    assert isinstance(result, str)
    assert "id" in result


def test_rebuild_picks_up_config_edit_and_closes_old(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    closed = _counting_close_all(monkeypatch)
    qcfg, dbcfg = _write_configs(tmp_path)
    old = build_toolset(qcfg, dbcfg)
    with qcfg.open("a", encoding="utf-8") as fh:
        fh.write('\n[queries.bar]\ndescription = "Bar"\nsql = "SELECT 1 AS x"\n')
    new = build_toolset(qcfg, dbcfg)
    old.close()
    try:
        assert "query_bar" in {s.name for s in new.specs}
        assert "query_bar" not in {s.name for s in old.specs}
        assert closed == [old.registry]
    finally:
        new.close()


def test_failed_build_closes_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    closed = _counting_close_all(monkeypatch)
    queries = (
        "\n[queries.bad]\n"
        'description = "Pinned to an unknown connection"\n'
        'connection = "nope"\n'
        'sql = "SELECT 1"\n'
    )
    qcfg, dbcfg = _write_configs(tmp_path, queries=queries)
    with pytest.raises(ValueError):
        build_toolset(qcfg, dbcfg)
    assert len(closed) == 1


@pytest.mark.asyncio
async def test_missing_descriptions_fall_back_and_verify_warns(
    tmp_path: Path,
) -> None:
    queries = '\n[queries.nodesc]\nsql = "SELECT * FROM customers"\n'
    updates = _UPDATES.replace('description = "Set customer name"\n', "")
    with build_toolset(
        *_write_configs(tmp_path, queries=queries, updates=updates)
    ) as toolset:
        specs = _by_name(toolset)
        assert specs["query_nodesc"].description == "Run configured query `nodesc`."
        assert (
            specs["update_set_name"].description == "Run configured update `set_name`."
        )
        text = await _call(specs["verify"], {})
    warn_lines = [line for line in text.splitlines() if line.startswith("[WARN]")]
    assert any("nodesc" in line and ".description" in line for line in warn_lines)
    assert any("set_name" in line and ".description" in line for line in warn_lines)


@pytest.mark.asyncio
async def test_verify_output_contains_neutral_note(tmp_path: Path) -> None:
    with build_toolset(*_write_configs(tmp_path)) as toolset:
        text = await _call(_by_name(toolset)["verify"], {})
    assert text.startswith("Config loaded.")
    assert "the running tools keep the config they were built with" in text
    assert "restart" not in text


def test_context_manager_closes_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    closed = _counting_close_all(monkeypatch)
    with build_toolset(*_write_configs(tmp_path)) as toolset:
        assert not closed
    assert closed == [toolset.registry]


_PROD_MSSQL = (
    '\n[connections.prod]\nbackend = "mssql"\nhost = "db1"\ndatabase = "app"\n'
)
_CHECK = "mcp_tools_sql.backends.connection_check"


def _no_registry(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Replace ``BackendRegistry`` in ``toolset`` with a mock to detect use."""
    registry = MagicMock()
    monkeypatch.setattr("mcp_tools_sql.toolset.BackendRegistry", registry)
    return registry


def _raise_import_error() -> str:
    raise ImportError("No module named 'pyodbc'")


def test_build_raises_when_pyodbc_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = _no_registry(monkeypatch)
    monkeypatch.setattr(f"{_CHECK}.pyodbc_version", _raise_import_error)
    qcfg, dbcfg = _write_configs(tmp_path, extra_connections=_PROD_MSSQL)
    with pytest.raises(ValueError, match=r"'prod'") as exc_info:
        build_toolset(qcfg, dbcfg)
    assert "[mssql]" in str(exc_info.value)
    registry.assert_not_called()


def test_build_raises_on_unsupported_backend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = _no_registry(monkeypatch)
    extra = '\n[connections.pg]\nbackend = "postgresql"\ndatabase = "x"\n'
    qcfg, dbcfg = _write_configs(tmp_path, extra_connections=extra)
    with pytest.raises(ValueError, match=r"'pg'") as exc_info:
        build_toolset(qcfg, dbcfg)
    assert "unsupported backend" in str(exc_info.value)
    registry.assert_not_called()


def test_build_raises_when_configured_driver_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = _no_registry(monkeypatch)
    monkeypatch.setattr(f"{_CHECK}.pyodbc_version", lambda: "5.2.0")
    monkeypatch.setattr(f"{_CHECK}.odbc_drivers", lambda: ["SQL Server"])
    extra = _PROD_MSSQL + 'driver = "ODBC Driver 99 for SQL Server"\n'
    qcfg, dbcfg = _write_configs(tmp_path, extra_connections=extra)
    with pytest.raises(ValueError, match="ODBC Driver 99 for SQL Server"):
        build_toolset(qcfg, dbcfg)
    registry.assert_not_called()


def test_build_raises_on_missing_explicit_database_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = _no_registry(monkeypatch)
    qcfg, _ = _write_configs(tmp_path)
    missing = tmp_path / "nope.toml"
    with pytest.raises(ValueError, match="nope.toml"):
        build_toolset(qcfg, missing)
    registry.assert_not_called()


def test_build_succeeds_with_mssql_dependencies_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(f"{_CHECK}.pyodbc_version", lambda: "5.2.0")
    monkeypatch.setattr(
        f"{_CHECK}.odbc_drivers", lambda: ["ODBC Driver 18 for SQL Server"]
    )
    qcfg, dbcfg = _write_configs(tmp_path, extra_connections=_PROD_MSSQL)
    with build_toolset(qcfg, dbcfg) as toolset:
        names = {s.name for s in toolset.specs}
    assert "query_foo" in names
    assert "read_databases" in names
