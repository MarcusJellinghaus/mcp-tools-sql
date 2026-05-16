"""Tests for the ValidationTools class and ``validate_sql`` tool."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import create_connected_server_and_client_session

from mcp_tools_sql.backends.mssql import MSSQLBackend
from mcp_tools_sql.backends.sqlite import SQLiteBackend
from mcp_tools_sql.config.models import ConnectionConfig
from mcp_tools_sql.validation_tools import ValidationTools, _explain
from tests.conftest import MSSQLTestEnv


def _sqlite_backend(db_path: Path) -> SQLiteBackend:
    """Return a connected SQLite backend for the given database path."""
    backend = SQLiteBackend(ConnectionConfig(backend="sqlite", path=str(db_path)))
    backend.connect()
    return backend


async def _call_validate(
    client: Any,
    sql: str,
    params: dict[str, Any] | None = None,
    return_plan: bool = False,
) -> str:
    """Call ``validate_sql`` via the MCP client and return the text content."""
    args: dict[str, Any] = {"sql": sql}
    if params is not None:
        args["params"] = params
    if return_plan:
        args["return_plan"] = return_plan
    result = await client.call_tool("validate_sql", args)
    return result.content[0].text  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------
# Pre-flight (no DB round-trip — spy on backend.explain via MagicMock)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_preflight_empty_sql(sqlite_db: Path) -> None:
    """Empty SQL is rejected before any DB round-trip."""
    backend = _sqlite_backend(sqlite_db)
    backend.explain = MagicMock()  # type: ignore[method-assign]
    mcp = FastMCP("test-preflight-empty")
    ValidationTools(backend, "sqlite").register(mcp)
    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        text = await _call_validate(client, "")
    assert text == "Invalid SQL. ValidationError: empty SQL"
    assert backend.explain.call_count == 0


@pytest.mark.asyncio
async def test_preflight_whitespace_only_sql(sqlite_db: Path) -> None:
    """Whitespace-only SQL is rejected as empty."""
    backend = _sqlite_backend(sqlite_db)
    backend.explain = MagicMock()  # type: ignore[method-assign]
    mcp = FastMCP("test-preflight-ws")
    ValidationTools(backend, "sqlite").register(mcp)
    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        text = await _call_validate(client, "   \n\t  ")
    assert text == "Invalid SQL. ValidationError: empty SQL"
    assert backend.explain.call_count == 0


@pytest.mark.asyncio
async def test_preflight_missing_param_with_params_none(sqlite_db: Path) -> None:
    """Missing param name with ``params=None`` is rejected."""
    backend = _sqlite_backend(sqlite_db)
    backend.explain = MagicMock()  # type: ignore[method-assign]
    mcp = FastMCP("test-preflight-missing-none")
    ValidationTools(backend, "sqlite").register(mcp)
    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        text = await _call_validate(client, "SELECT :x")
    assert text == "Invalid parameters. ValidationError: missing parameter: x"
    assert backend.explain.call_count == 0


@pytest.mark.asyncio
async def test_preflight_missing_param_with_empty_params(sqlite_db: Path) -> None:
    """Missing param name with ``params={}`` hits the same pre-flight rejection."""
    backend = _sqlite_backend(sqlite_db)
    backend.explain = MagicMock()  # type: ignore[method-assign]
    mcp = FastMCP("test-preflight-missing-empty")
    ValidationTools(backend, "sqlite").register(mcp)
    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        text = await _call_validate(client, "SELECT :x", params={})
    assert text == "Invalid parameters. ValidationError: missing parameter: x"
    assert backend.explain.call_count == 0


@pytest.mark.asyncio
async def test_preflight_multi_statement(sqlite_db: Path) -> None:
    """Multi-statement SQL is rejected without a DB round-trip."""
    backend = _sqlite_backend(sqlite_db)
    backend.explain = MagicMock()  # type: ignore[method-assign]
    mcp = FastMCP("test-preflight-multi")
    ValidationTools(backend, "sqlite").register(mcp)
    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        text = await _call_validate(client, "SELECT 1; SELECT 2")
    assert text == "Invalid SQL. ValidationError: multiple statements not supported"
    assert backend.explain.call_count == 0


@pytest.mark.asyncio
async def test_preflight_use_statement(sqlite_db: Path) -> None:
    """``USE other_db`` is rejected as a session-control statement."""
    backend = _sqlite_backend(sqlite_db)
    backend.explain = MagicMock()  # type: ignore[method-assign]
    mcp = FastMCP("test-preflight-use")
    ValidationTools(backend, "sqlite").register(mcp)
    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        text = await _call_validate(client, "USE other_db")
    assert text == "Invalid SQL. ValidationError: USE statements not supported"
    assert backend.explain.call_count == 0


@pytest.mark.asyncio
async def test_preflight_set_statement(sqlite_db: Path) -> None:
    """``SET QUOTED_IDENTIFIER ON`` is rejected as a session-control statement."""
    backend = _sqlite_backend(sqlite_db)
    backend.explain = MagicMock()  # type: ignore[method-assign]
    mcp = FastMCP("test-preflight-set")
    ValidationTools(backend, "sqlite").register(mcp)
    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        text = await _call_validate(client, "SET QUOTED_IDENTIFIER ON")
    assert text == "Invalid SQL. ValidationError: SET statements not supported"
    assert backend.explain.call_count == 0


@pytest.mark.asyncio
async def test_preflight_declare_statement(sqlite_db: Path) -> None:
    """``DECLARE @x INT`` is rejected as a session-control statement."""
    backend = _sqlite_backend(sqlite_db)
    backend.explain = MagicMock()  # type: ignore[method-assign]
    mcp = FastMCP("test-preflight-declare")
    ValidationTools(backend, "sqlite").register(mcp)
    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        text = await _call_validate(client, "DECLARE @x INT")
    assert text == "Invalid SQL. ValidationError: DECLARE statements not supported"
    assert backend.explain.call_count == 0


# ---------------------------------------------------------------------------
# MSSQL _explain unit test (mocked)
# ---------------------------------------------------------------------------


def test_mssql_explain_showplan_sequence() -> None:
    """``_explain`` MSSQL branch runs the SHOWPLAN dance in the right order."""
    cursor = MagicMock()
    cursor.fetchall.return_value = [("StmtText",), ("plan-row-1",)]
    conn = MagicMock()
    conn.cursor.return_value = cursor

    isolated_cm = MagicMock()
    isolated_cm.__enter__ = MagicMock(return_value=conn)
    isolated_cm.__exit__ = MagicMock(return_value=False)

    backend = MagicMock()
    backend.get_isolated_connection = MagicMock(return_value=isolated_cm)

    plan = _explain(backend, "mssql", "SELECT :a", {"a": 1})

    assert plan == "StmtText\nplan-row-1"
    call_sequence = [call.args[0] for call in cursor.execute.call_args_list]
    assert call_sequence == [
        "SET SHOWPLAN_TEXT ON",
        "SELECT 1",
        "SET SHOWPLAN_TEXT OFF",
    ]
    # execute(explain_sql) was called positionally without a params argument.
    explain_call = cursor.execute.call_args_list[1]
    assert explain_call.args == ("SELECT 1",)
    assert explain_call.kwargs == {}
    cursor.close.assert_called_once()


def test_mssql_explain_showplan_off_runs_on_execute_failure() -> None:
    """``SET SHOWPLAN_TEXT OFF`` still runs when the explained statement raises."""
    cursor = MagicMock()

    def execute_side_effect(sql: str, *_: Any, **__: Any) -> None:
        if sql == "SELECT bogus":
            raise RuntimeError("explain failed")

    cursor.execute.side_effect = execute_side_effect
    conn = MagicMock()
    conn.cursor.return_value = cursor

    isolated_cm = MagicMock()
    isolated_cm.__enter__ = MagicMock(return_value=conn)
    isolated_cm.__exit__ = MagicMock(return_value=False)

    backend = MagicMock()
    backend.get_isolated_connection = MagicMock(return_value=isolated_cm)

    with pytest.raises(RuntimeError, match="explain failed"):
        _explain(backend, "mssql", "SELECT bogus", None)

    call_sequence = [call.args[0] for call in cursor.execute.call_args_list]
    assert call_sequence == [
        "SET SHOWPLAN_TEXT ON",
        "SELECT bogus",
        "SET SHOWPLAN_TEXT OFF",
    ]
    cursor.close.assert_called_once()


# ---------------------------------------------------------------------------
# Param handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_params_none_no_placeholders(sqlite_db: Path) -> None:
    """``params=None`` against non-parameterised SQL returns ``Valid.``."""
    backend = _sqlite_backend(sqlite_db)
    mcp = FastMCP("test-params-none")
    ValidationTools(backend, "sqlite").register(mcp)
    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        text = await _call_validate(client, "SELECT 1")
    assert text == "Valid."


@pytest.mark.asyncio
async def test_params_empty_no_placeholders(sqlite_db: Path) -> None:
    """``params={}`` against non-parameterised SQL returns ``Valid.``."""
    backend = _sqlite_backend(sqlite_db)
    mcp = FastMCP("test-params-empty")
    ValidationTools(backend, "sqlite").register(mcp)
    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        text = await _call_validate(client, "SELECT 1", params={})
    assert text == "Valid."


@pytest.mark.asyncio
async def test_extra_params_silently_ignored(sqlite_db: Path) -> None:
    """Extra param names in ``params`` (not in SQL) are silently ignored."""
    backend = _sqlite_backend(sqlite_db)
    mcp = FastMCP("test-params-extra")
    ValidationTools(backend, "sqlite").register(mcp)
    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        text = await _call_validate(client, "SELECT 1", params={"unused": "value"})
    assert text == "Valid."


@pytest.mark.asyncio
async def test_extras_tolerated_alongside_required(sqlite_db: Path) -> None:
    """Extra param keys are tolerated when all referenced placeholders are bound."""
    backend = _sqlite_backend(sqlite_db)
    mcp = FastMCP("test-params-extras-required")
    ValidationTools(backend, "sqlite").register(mcp)
    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        text = await _call_validate(client, "SELECT :a", params={"a": 1, "b": 2})
    assert text == "Valid."


# ---------------------------------------------------------------------------
# Success (via sqlite_db fixture)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_valid_select_default(sqlite_db: Path) -> None:
    """A valid SELECT returns ``Valid.`` (no plan by default)."""
    backend = _sqlite_backend(sqlite_db)
    mcp = FastMCP("test-valid-select")
    ValidationTools(backend, "sqlite").register(mcp)
    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        text = await _call_validate(client, "SELECT * FROM customers")
    assert text == "Valid."


@pytest.mark.asyncio
async def test_valid_select_with_return_plan(sqlite_db: Path) -> None:
    """``return_plan=True`` appends the execution plan on success."""
    backend = _sqlite_backend(sqlite_db)
    mcp = FastMCP("test-valid-select-plan")
    ValidationTools(backend, "sqlite").register(mcp)
    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        text = await _call_validate(client, "SELECT * FROM customers", return_plan=True)
    assert text.startswith("Valid.\nExecution plan:\n")
    plan_text = text[len("Valid.\nExecution plan:\n") :]
    assert plan_text.strip() != ""


@pytest.mark.asyncio
async def test_valid_update_does_not_execute(sqlite_db: Path) -> None:
    """A valid UPDATE returns ``Valid.`` but does not actually run."""
    backend = _sqlite_backend(sqlite_db)
    mcp = FastMCP("test-valid-update")
    ValidationTools(backend, "sqlite").register(mcp)
    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        text = await _call_validate(
            client, "UPDATE customers SET name = 'X' WHERE id = 999"
        )
    assert text == "Valid."
    rows = backend.execute_query("SELECT id FROM customers WHERE id = 999")
    assert rows == []


@pytest.mark.asyncio
async def test_valid_ddl_does_not_execute(sqlite_db: Path) -> None:
    """A valid DDL returns ``Valid.`` but the schema is untouched."""
    backend = _sqlite_backend(sqlite_db)
    mcp = FastMCP("test-valid-ddl")
    ValidationTools(backend, "sqlite").register(mcp)
    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        text = await _call_validate(client, "DROP TABLE customers")
    assert text == "Valid."
    rows = backend.execute_query(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='customers'"
    )
    assert len(rows) == 1


# ---------------------------------------------------------------------------
# Failure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_syntax_error(sqlite_db: Path) -> None:
    """Syntax error yields ``Invalid SQL. ...`` with the sqlite3 type name."""
    backend = _sqlite_backend(sqlite_db)
    mcp = FastMCP("test-syntax-error")
    ValidationTools(backend, "sqlite").register(mcp)
    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        text = await _call_validate(client, "SELEKT * FROM customers")
    assert text.startswith("Invalid SQL. ")
    assert "OperationalError" in text


@pytest.mark.asyncio
async def test_unknown_table(sqlite_db: Path) -> None:
    """Unknown table yields ``Invalid SQL. ...``."""
    backend = _sqlite_backend(sqlite_db)
    mcp = FastMCP("test-unknown-table")
    ValidationTools(backend, "sqlite").register(mcp)
    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        text = await _call_validate(client, "SELECT * FROM no_such_table")
    assert text.startswith("Invalid SQL. ")


@pytest.mark.asyncio
async def test_return_plan_on_invalid_sql_omits_plan(sqlite_db: Path) -> None:
    """``return_plan=True`` on invalid SQL returns only the error verdict."""
    backend = _sqlite_backend(sqlite_db)
    mcp = FastMCP("test-invalid-plan")
    ValidationTools(backend, "sqlite").register(mcp)
    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        text = await _call_validate(client, "SELEKT * FROM customers", return_plan=True)
    assert text.startswith("Invalid SQL. ")
    assert "Execution plan:" not in text


@pytest.mark.asyncio
async def test_runtime_error_after_close(sqlite_db: Path) -> None:
    """``RuntimeError`` (backend closed) maps to ``Database connection error.``"""
    backend = _sqlite_backend(sqlite_db)
    mcp = FastMCP("test-runtime-error")
    ValidationTools(backend, "sqlite").register(mcp)
    backend.close()
    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        text = await _call_validate(client, "SELECT 1")
    assert text.startswith("Database connection error. RuntimeError: ")


# ---------------------------------------------------------------------------
# MSSQL integration (skipped automatically when TEST_MSSQL_* env vars are missing)
# ---------------------------------------------------------------------------


@pytest.mark.mssql_integration
@pytest.mark.asyncio
async def test_mssql_valid_select(mssql_db: MSSQLTestEnv) -> None:
    """A valid SELECT against the seeded schema returns ``Valid.``."""
    backend = MSSQLBackend(mssql_db.config)
    try:
        mcp = FastMCP("test-mssql-valid-select")
        ValidationTools(backend, "mssql").register(mcp)
        async with create_connected_server_and_client_session(
            mcp, raise_exceptions=True
        ) as client:
            text = await _call_validate(
                client, f"SELECT * FROM {mssql_db.schema}.customers"
            )
        assert text == "Valid."
    finally:
        backend.close()


@pytest.mark.mssql_integration
@pytest.mark.asyncio
async def test_mssql_valid_select_return_plan(mssql_db: MSSQLTestEnv) -> None:
    """``return_plan=True`` appends a non-empty execution plan on success."""
    backend = MSSQLBackend(mssql_db.config)
    try:
        mcp = FastMCP("test-mssql-valid-select-plan")
        ValidationTools(backend, "mssql").register(mcp)
        async with create_connected_server_and_client_session(
            mcp, raise_exceptions=True
        ) as client:
            text = await _call_validate(
                client,
                f"SELECT * FROM {mssql_db.schema}.customers",
                return_plan=True,
            )
        assert text.startswith("Valid.\nExecution plan:\n")
        plan_text = text[len("Valid.\nExecution plan:\n") :]
        assert plan_text.strip() != ""
    finally:
        backend.close()


@pytest.mark.mssql_integration
@pytest.mark.asyncio
async def test_mssql_syntax_error(mssql_db: MSSQLTestEnv) -> None:
    """Invalid syntax returns ``Invalid SQL. ...``."""
    backend = MSSQLBackend(mssql_db.config)
    try:
        mcp = FastMCP("test-mssql-syntax-error")
        ValidationTools(backend, "mssql").register(mcp)
        async with create_connected_server_and_client_session(
            mcp, raise_exceptions=True
        ) as client:
            text = await _call_validate(
                client, f"SELEKT * FROM {mssql_db.schema}.customers"
            )
        assert text.startswith("Invalid SQL. ")
    finally:
        backend.close()


@pytest.mark.mssql_integration
@pytest.mark.asyncio
async def test_mssql_unknown_table(mssql_db: MSSQLTestEnv) -> None:
    """Unknown table returns ``Invalid SQL. ...``."""
    backend = MSSQLBackend(mssql_db.config)
    try:
        mcp = FastMCP("test-mssql-unknown-table")
        ValidationTools(backend, "mssql").register(mcp)
        async with create_connected_server_and_client_session(
            mcp, raise_exceptions=True
        ) as client:
            text = await _call_validate(
                client, f"SELECT * FROM {mssql_db.schema}.no_such_table"
            )
        assert text.startswith("Invalid SQL. ")
    finally:
        backend.close()


@pytest.mark.mssql_integration
@pytest.mark.asyncio
async def test_mssql_unsupported_param_type(mssql_db: MSSQLTestEnv) -> None:
    """``set()`` is rejected with ``Invalid parameters. TypeError: ...``."""
    backend = MSSQLBackend(mssql_db.config)
    try:
        mcp = FastMCP("test-mssql-unsupported-param")
        ValidationTools(backend, "mssql").register(mcp)
        async with create_connected_server_and_client_session(
            mcp, raise_exceptions=True
        ) as client:
            text = await _call_validate(client, "SELECT :x", params={"x": set()})
        assert text.startswith("Invalid parameters. TypeError: ")
    finally:
        backend.close()


@pytest.mark.mssql_integration
@pytest.mark.asyncio
async def test_mssql_non_finite_float(mssql_db: MSSQLTestEnv) -> None:
    """``float('inf')`` is rejected with ``Invalid parameters. ValueError: ...``."""
    backend = MSSQLBackend(mssql_db.config)
    try:
        mcp = FastMCP("test-mssql-non-finite-float")
        ValidationTools(backend, "mssql").register(mcp)
        async with create_connected_server_and_client_session(
            mcp, raise_exceptions=True
        ) as client:
            text = await _call_validate(client, "SELECT :x", params={"x": float("inf")})
        assert text.startswith("Invalid parameters. ValueError: ")
    finally:
        backend.close()


@pytest.mark.mssql_integration
@pytest.mark.asyncio
async def test_mssql_valid_update_does_not_execute(mssql_db: MSSQLTestEnv) -> None:
    """A valid UPDATE returns ``Valid.`` without running on MSSQL."""
    backend = MSSQLBackend(mssql_db.config)
    try:
        mcp = FastMCP("test-mssql-valid-update")
        ValidationTools(backend, "mssql").register(mcp)
        rows_before = backend.execute_query(
            f"SELECT COUNT(*) AS n FROM {mssql_db.schema}.customers WHERE id = 999"
        )
        assert rows_before == [{"n": 0}]
        async with create_connected_server_and_client_session(
            mcp, raise_exceptions=True
        ) as client:
            text = await _call_validate(
                client,
                f"UPDATE {mssql_db.schema}.customers " "SET name = 'X' WHERE id = 999",
            )
        assert text == "Valid."
        rows_after = backend.execute_query(
            f"SELECT COUNT(*) AS n FROM {mssql_db.schema}.customers WHERE id = 999"
        )
        assert rows_after == [{"n": 0}]
    finally:
        backend.close()


@pytest.mark.mssql_integration
@pytest.mark.asyncio
async def test_mssql_session_state_containment(mssql_db: MSSQLTestEnv) -> None:
    """The persistent connection's ``DB_NAME()`` is unchanged across validate_sql."""
    backend = MSSQLBackend(mssql_db.config)
    try:
        mcp = FastMCP("test-mssql-session-state")
        ValidationTools(backend, "mssql").register(mcp)
        async with create_connected_server_and_client_session(
            mcp, raise_exceptions=True
        ) as client:
            text = await _call_validate(
                client, f"SELECT * FROM {mssql_db.schema}.customers"
            )
        assert text == "Valid."
        rows = backend.execute_query("SELECT DB_NAME() AS db")
        assert rows == [{"db": mssql_db.config.database}]
    finally:
        backend.close()
