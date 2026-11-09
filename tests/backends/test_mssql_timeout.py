"""Login/statement timeout tests for the MSSQL backend."""

from __future__ import annotations

from typing import Any

import pytest

from mcp_tools_sql.backends.base import QueryTimeoutError
from mcp_tools_sql.backends.mssql import MSSQLBackend
from tests.backends.conftest import _cfg


class TestConnectionTimeouts:
    """Login timeout via connect(timeout=...), statement timeout via conn.timeout."""

    def test_connect_uses_default_timeouts(self, fake_pyodbc: Any) -> None:
        b = MSSQLBackend(_cfg())
        b.connect()
        assert fake_pyodbc.connect.call_args.kwargs["timeout"] == 15
        assert fake_pyodbc.connect.return_value.timeout == 30

    def test_connect_uses_configured_timeouts(self, fake_pyodbc: Any) -> None:
        b = MSSQLBackend(_cfg(connect_timeout_seconds=7, query_timeout_seconds=4))
        b.connect()
        assert fake_pyodbc.connect.call_args.kwargs["timeout"] == 7
        assert fake_pyodbc.connect.return_value.timeout == 4

    def test_isolated_connection_default_timeouts(self, fake_pyodbc: Any) -> None:
        b = MSSQLBackend(_cfg())
        with b.get_isolated_connection() as conn:
            assert conn.timeout == 30
        assert fake_pyodbc.connect.call_args.kwargs["timeout"] == 15

    def test_isolated_connection_configured_timeouts(self, fake_pyodbc: Any) -> None:
        b = MSSQLBackend(_cfg(connect_timeout_seconds=7, query_timeout_seconds=4))
        with b.get_isolated_connection() as conn:
            assert conn.timeout == 4
        assert fake_pyodbc.connect.call_args.kwargs["timeout"] == 7


class TestStatementTimeoutTranslation:
    """HYT00 from execute/fetch becomes QueryTimeoutError; nothing else does."""

    @pytest.mark.parametrize(
        "call",
        [
            lambda b: b.execute_query("SELECT 1"),
            lambda b: b.execute_readonly_query_with_columns("SELECT 1"),
            lambda b: b.execute_update("UPDATE t SET x = 1"),
            lambda b: b.explain("SELECT 1"),
        ],
        ids=["execute_query", "with_columns", "execute_update", "explain"],
    )
    def test_execute_hyt00_raises_query_timeout(
        self, fake_pyodbc: Any, call: Any
    ) -> None:
        cur = fake_pyodbc.connect.return_value.cursor.return_value
        cur.execute.side_effect = fake_pyodbc.OperationalError("HYT00", "timeout")
        b = MSSQLBackend(_cfg(query_timeout_seconds=5))
        with pytest.raises(QueryTimeoutError) as info:
            call(b)
        assert info.value.seconds == 5
        assert isinstance(info.value.__cause__, fake_pyodbc.OperationalError)

    @pytest.mark.parametrize(
        "call",
        [
            lambda b: b.execute_query("SELECT 1"),
            lambda b: b.execute_readonly_query_with_columns("SELECT 1"),
            lambda b: b.explain("SELECT 1"),
        ],
        ids=["execute_query", "with_columns", "explain"],
    )
    def test_fetch_hyt00_raises_query_timeout(
        self, fake_pyodbc: Any, call: Any
    ) -> None:
        cur = fake_pyodbc.connect.return_value.cursor.return_value
        cur.description = [("col",)]
        cur.fetchall.side_effect = fake_pyodbc.OperationalError("HYT00", "timeout")
        b = MSSQLBackend(_cfg())
        with pytest.raises(QueryTimeoutError):
            call(b)

    def test_other_sqlstate_propagates_unchanged(self, fake_pyodbc: Any) -> None:
        cur = fake_pyodbc.connect.return_value.cursor.return_value
        err = fake_pyodbc.OperationalError("42000", "syntax error")
        cur.execute.side_effect = err
        b = MSSQLBackend(_cfg())
        with pytest.raises(fake_pyodbc.OperationalError) as info:
            b.execute_query("SELECT 1")
        assert info.value is err

    def test_login_hyt00_not_translated(self, fake_pyodbc: Any) -> None:
        fake_pyodbc.connect.side_effect = fake_pyodbc.OperationalError(
            "HYT00", "login timeout"
        )
        b = MSSQLBackend(_cfg())
        with pytest.raises(fake_pyodbc.OperationalError) as info:
            b.execute_query("SELECT 1")
        assert not isinstance(info.value, QueryTimeoutError)
        assert info.value.args[0] == "HYT00"

    def test_isolated_login_hyt00_not_translated(self, fake_pyodbc: Any) -> None:
        fake_pyodbc.connect.side_effect = fake_pyodbc.OperationalError(
            "HYT00", "login timeout"
        )
        b = MSSQLBackend(_cfg())
        with pytest.raises(fake_pyodbc.OperationalError):
            with b.get_isolated_connection():
                pass
