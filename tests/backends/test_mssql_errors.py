"""Driver-error translation tests for the MSSQL backend."""

from __future__ import annotations

import importlib
import sys
from typing import Any

import pytest

from mcp_tools_sql.backends.base import (
    BackendConnectionError,
    BackendError,
    QueryTimeoutError,
)
from mcp_tools_sql.backends.mssql import MSSQLBackend, _odbc_escape
from mcp_tools_sql.sql_ast.placeholders import SqlParseError
from tests.backends.conftest import LEAKY_PASSWORDS, _cfg, assert_no_leak


class TestCursorErrors:
    """pyodbc errors from cursor work become neutral backend errors."""

    def test_error_becomes_backend_error(self, fake_pyodbc: Any) -> None:
        cur = fake_pyodbc.connect.return_value.cursor.return_value
        err = fake_pyodbc.Error("42000", "bad")
        cur.execute.side_effect = err
        with pytest.raises(BackendError) as info:
            MSSQLBackend(_cfg()).execute_query("SELECT 1")
        assert not isinstance(info.value, BackendConnectionError)
        assert info.value.original_class == "Error"
        assert str(info.value) == str(fake_pyodbc.Error("42000", "bad"))
        assert info.value.__cause__ is err

    @pytest.mark.parametrize("name", ["OperationalError", "InterfaceError"])
    def test_connection_shaped_errors(self, fake_pyodbc: Any, name: str) -> None:
        cur = fake_pyodbc.connect.return_value.cursor.return_value
        cur.execute.side_effect = getattr(fake_pyodbc, name)("08S01", "link")
        with pytest.raises(BackendConnectionError) as info:
            MSSQLBackend(_cfg()).execute_query("SELECT 1")
        assert info.value.original_class == name
        assert info.value.args == ("08S01", "link")

    def test_statement_hyt00_is_query_timeout(self, fake_pyodbc: Any) -> None:
        cur = fake_pyodbc.connect.return_value.cursor.return_value
        cur.execute.side_effect = fake_pyodbc.OperationalError("HYT00", "timeout")
        with pytest.raises(QueryTimeoutError):
            MSSQLBackend(_cfg()).execute_query("SELECT 1")

    @pytest.mark.parametrize(
        "call",
        [
            lambda b: b.execute_query("SELECT 1"),
            lambda b: b.execute_readonly_query_with_columns("SELECT 1"),
            lambda b: b.execute_update("UPDATE t SET x = 1"),
            lambda b: b.explain("SELECT 1"),
            lambda b: next(b.iter_readonly_batches("SELECT 1")),
        ],
        ids=["execute_query", "with_columns", "execute_update", "explain", "batches"],
    )
    def test_cursor_creation_error_translated(
        self, fake_pyodbc: Any, call: Any
    ) -> None:
        conn = fake_pyodbc.connect.return_value
        conn.cursor.side_effect = fake_pyodbc.Error("HY000", "no cursor")
        with pytest.raises(BackendError) as info:
            call(MSSQLBackend(_cfg()))
        assert info.value.original_class == "Error"

    def test_batches_fetch_error_translated(self, fake_pyodbc: Any) -> None:
        cur = fake_pyodbc.connect.return_value.cursor.return_value
        cur.description = [("a",)]
        cur.fetchmany.side_effect = fake_pyodbc.Error("42000", "bad")
        gen = MSSQLBackend(_cfg()).iter_readonly_batches("SELECT a FROM t")
        with pytest.raises(BackendError):
            next(gen)
        cur.close.assert_called_once()

    def test_close_error_translated(self, fake_pyodbc: Any) -> None:
        conn = fake_pyodbc.connect.return_value
        conn.close.side_effect = fake_pyodbc.OperationalError("08S01", "gone")
        b = MSSQLBackend(_cfg())
        b.connect()
        with pytest.raises(BackendConnectionError):
            b.close()


class TestConnectErrors:
    """pyodbc errors from connect() become BackendConnectionError, redacted."""

    def test_login_hyt00_is_connection_error(self, fake_pyodbc: Any) -> None:
        fake_pyodbc.connect.side_effect = fake_pyodbc.OperationalError(
            "HYT00", "login timeout"
        )
        with pytest.raises(BackendConnectionError) as info:
            MSSQLBackend(_cfg()).execute_query("SELECT 1")
        assert not isinstance(info.value, QueryTimeoutError)
        assert info.value.args[0] == "HYT00"

    @pytest.mark.parametrize("password", LEAKY_PASSWORDS)
    def test_password_redacted(self, fake_pyodbc: Any, password: str) -> None:
        fake_pyodbc.connect.side_effect = fake_pyodbc.OperationalError(
            "08001", f"Login failed; PWD={_odbc_escape(password)}"
        )
        with pytest.raises(BackendConnectionError) as info:
            MSSQLBackend(_cfg(password=password)).connect()
        assert_no_leak(str(info.value), password)
        assert "***" in str(info.value)


class TestUntouched:
    """Non-driver exceptions pass through unchanged."""

    def test_missing_param_keyerror(self, fake_pyodbc: Any) -> None:
        with pytest.raises(KeyError, match="x"):
            MSSQLBackend(_cfg()).execute_query("SELECT :x", None)

    def test_sql_parse_error(
        self, fake_pyodbc: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _boom(sql: str, dialect: str) -> Any:
            raise SqlParseError("bad sql", original_class="ParseError")

        monkeypatch.setattr(
            "mcp_tools_sql.backends.mssql.translate_named_to_qmark", _boom
        )
        with pytest.raises(SqlParseError):
            MSSQLBackend(_cfg()).execute_query("SELECT 1")

    def test_runtime_error_from_cursor(self, fake_pyodbc: Any) -> None:
        cur = fake_pyodbc.connect.return_value.cursor.return_value
        cur.execute.side_effect = RuntimeError("boom")
        with pytest.raises(RuntimeError, match="boom"):
            MSSQLBackend(_cfg()).execute_query("SELECT 1")


def test_module_imports_without_pyodbc(monkeypatch: pytest.MonkeyPatch) -> None:
    """The backend module never imports pyodbc at module scope."""
    package = importlib.import_module("mcp_tools_sql.backends")
    # Restore the package attribute too, so later dotted-path patches still
    # resolve to the original module object.
    monkeypatch.setattr(package, "mssql", sys.modules["mcp_tools_sql.backends.mssql"])
    monkeypatch.setitem(sys.modules, "pyodbc", None)
    monkeypatch.delitem(sys.modules, "mcp_tools_sql.backends.mssql")
    module = importlib.import_module("mcp_tools_sql.backends.mssql")
    assert hasattr(module, "MSSQLBackend")
