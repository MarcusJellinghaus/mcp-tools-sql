"""SHOWPLAN tests for ``MSSQLBackend.explain`` (driven by ``fake_pyodbc``)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from mcp_tools_sql.backends.base import (
    BackendConnectionError,
    BackendError,
    QueryTimeoutError,
)
from mcp_tools_sql.backends.mssql import MSSQLBackend
from tests.backends.conftest import _cfg


def _fail_statement(fake_pyodbc: Any, exc: Exception) -> MagicMock:
    """Make the explained statement (not the SHOWPLAN toggles) raise ``exc``.

    Returns:
        The cursor of the fake connection.
    """
    cursor = fake_pyodbc.connect.return_value.cursor.return_value

    def execute_side_effect(sql: str, *_: Any, **__: Any) -> None:
        if not sql.startswith("SET SHOWPLAN_TEXT"):
            raise exc

    cursor.execute.side_effect = execute_side_effect
    return cursor  # type: ignore[no-any-return]


class TestIsolatedExplain:
    """``explain(..., isolated=True)`` runs SHOWPLAN on a fresh connection."""

    def test_showplan_sequence(self, fake_pyodbc: Any) -> None:
        conn = fake_pyodbc.connect.return_value
        cursor = conn.cursor.return_value
        cursor.fetchall.return_value = [("StmtText",), ("plan-row-1",)]
        b = MSSQLBackend(_cfg())

        plan = b.explain("SELECT :a", {"a": 1}, isolated=True)

        assert plan == "StmtText\nplan-row-1"
        fake_pyodbc.connect.assert_called_once()
        call_sequence = [call.args[0] for call in cursor.execute.call_args_list]
        assert call_sequence == [
            "SET SHOWPLAN_TEXT ON",
            "SELECT 1",
            "SET SHOWPLAN_TEXT OFF",
        ]
        explain_call = cursor.execute.call_args_list[1]
        assert explain_call.args == ("SELECT 1",)
        assert explain_call.kwargs == {}
        cursor.close.assert_called_once()
        conn.close.assert_called_once()

    def test_showplan_off_runs_on_execute_failure(self, fake_pyodbc: Any) -> None:
        cursor = _fail_statement(fake_pyodbc, RuntimeError("explain failed"))
        b = MSSQLBackend(_cfg())

        with pytest.raises(RuntimeError, match="explain failed"):
            b.explain("SELECT bogus", None, isolated=True)

        call_sequence = [call.args[0] for call in cursor.execute.call_args_list]
        assert call_sequence == [
            "SET SHOWPLAN_TEXT ON",
            "SELECT bogus",
            "SET SHOWPLAN_TEXT OFF",
        ]
        cursor.close.assert_called_once()
        fake_pyodbc.connect.return_value.close.assert_called_once()

    def test_non_finite_float_raises_before_connect(self, fake_pyodbc: Any) -> None:
        b = MSSQLBackend(_cfg())
        with pytest.raises(ValueError, match="non-finite"):
            b.explain("SELECT :x", {"x": float("inf")}, isolated=True)
        fake_pyodbc.connect.assert_not_called()

    def test_isolated_works_after_close(self, fake_pyodbc: Any) -> None:
        cursor = fake_pyodbc.connect.return_value.cursor.return_value
        cursor.fetchall.return_value = [("plan",)]
        b = MSSQLBackend(_cfg())
        b.close()

        assert b.explain("SELECT 1", isolated=True) == "plan"
        with pytest.raises(RuntimeError):
            b.explain("SELECT 1")

    def test_statement_hyt00_is_query_timeout(self, fake_pyodbc: Any) -> None:
        _fail_statement(fake_pyodbc, fake_pyodbc.OperationalError("HYT00", "timeout"))
        b = MSSQLBackend(_cfg(query_timeout_seconds=30))
        with pytest.raises(QueryTimeoutError) as info:
            b.explain("SELECT 1", isolated=True)
        assert info.value.seconds == 30

    def test_login_hyt00_is_connection_error(self, fake_pyodbc: Any) -> None:
        fake_pyodbc.connect.side_effect = fake_pyodbc.OperationalError(
            "HYT00", "login timeout"
        )
        b = MSSQLBackend(_cfg())
        with pytest.raises(BackendConnectionError) as info:
            b.explain("SELECT 1", isolated=True)
        assert not isinstance(info.value, QueryTimeoutError)

    def test_other_sqlstate_is_backend_error(self, fake_pyodbc: Any) -> None:
        original = fake_pyodbc.Error("42000", "driver message")
        _fail_statement(fake_pyodbc, original)
        b = MSSQLBackend(_cfg())
        with pytest.raises(BackendError) as info:
            b.explain("SELECT 1", isolated=True)
        assert not isinstance(info.value, QueryTimeoutError)
        assert info.value.original_class == "Error"
        assert str(info.value) == str(original)

    def test_close_error_is_backend_error(self, fake_pyodbc: Any) -> None:
        conn = fake_pyodbc.connect.return_value
        conn.cursor.return_value.fetchall.return_value = []
        conn.close.side_effect = fake_pyodbc.Error("HY000", "close failed")
        b = MSSQLBackend(_cfg())
        with pytest.raises(BackendError) as info:
            b.explain("SELECT 1", isolated=True)
        assert info.value.original_class == "Error"
