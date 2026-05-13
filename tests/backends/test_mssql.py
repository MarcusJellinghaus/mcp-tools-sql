"""Unit tests for MSSQL connection-string builder helpers and backend."""

from __future__ import annotations

import sys
import threading
import types
from typing import Any
from unittest.mock import MagicMock

import pytest

from mcp_tools_sql.backends.mssql import (
    MSSQLBackend,
    _build_connection_string,
    _odbc_escape,
)
from mcp_tools_sql.config.models import ConnectionConfig


@pytest.fixture
def fake_pyodbc(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Replace pyodbc with a fake module exposing connect() returning a Mock."""
    fake = types.ModuleType("pyodbc")
    fake.Error = type("Error", (Exception,), {})  # type: ignore[attr-defined]
    fake.connect = MagicMock(  # type: ignore[attr-defined]
        return_value=MagicMock(name="connection")
    )
    monkeypatch.setitem(sys.modules, "pyodbc", fake)
    return fake


def _cfg(**kw: Any) -> ConnectionConfig:
    """Build a ConnectionConfig with sensible defaults for tests."""
    base: dict[str, Any] = {
        "backend": "mssql",
        "host": "h",
        "port": 1433,
        "database": "d",
        "username": "u",
        "password": "p",
    }
    base.update(kw)
    return ConnectionConfig(**base)


class TestOdbcEscape:
    """Tests for `_odbc_escape`."""

    def test_plain_value_unchanged(self) -> None:
        assert _odbc_escape("plain") == "plain"

    def test_value_with_semicolon_wrapped(self) -> None:
        assert _odbc_escape("a;b") == "{a;b}"

    def test_value_with_equals_wrapped(self) -> None:
        assert _odbc_escape("a=b") == "{a=b}"

    def test_value_with_opening_brace_wrapped(self) -> None:
        assert _odbc_escape("a{b") == "{a{b}"

    def test_value_with_closing_brace_doubled(self) -> None:
        assert _odbc_escape("a}b") == "{a}}b}"

    def test_value_with_leading_space_wrapped(self) -> None:
        assert _odbc_escape(" a") == "{ a}"

    def test_value_with_trailing_space_wrapped(self) -> None:
        assert _odbc_escape("a ") == "{a }"

    def test_empty_value_returned_empty(self) -> None:
        assert _odbc_escape("") == ""


class TestConnectionStringBuilder:
    """Tests for `_build_connection_string`."""

    def test_password_auth_basic(self) -> None:
        c = ConnectionConfig(
            backend="mssql",
            host="h",
            port=1433,
            database="d",
            username="u",
            password="p",
        )
        s = _build_connection_string(c)
        assert "Server=h,1433" in s
        assert "UID=u" in s and "PWD=p" in s
        assert "Trusted_Connection" not in s
        assert "Encrypt=yes" in s
        assert "TrustServerCertificate=no" in s

    def test_trusted_connection_omits_uid_pwd(self) -> None:
        c = ConnectionConfig(
            backend="mssql",
            host="h",
            port=1433,
            database="d",
            trusted_connection=True,
        )
        s = _build_connection_string(c)
        assert "Trusted_Connection=yes" in s
        assert "UID=" not in s and "PWD=" not in s

    def test_port_zero_defaults_to_1433(self) -> None:
        c = ConnectionConfig(
            backend="mssql",
            host="h",
            port=0,
            database="d",
            trusted_connection=True,
        )
        assert "Server=h,1433" in _build_connection_string(c)

    def test_port_uses_comma_not_colon(self) -> None:
        c = ConnectionConfig(
            backend="mssql",
            host="h",
            port=1234,
            database="d",
            trusted_connection=True,
        )
        s = _build_connection_string(c)
        assert "Server=h,1234" in s
        assert "h:1234" not in s

    def test_password_with_semicolon_escaped(self) -> None:
        c = ConnectionConfig(
            backend="mssql",
            host="h",
            port=1433,
            database="d",
            username="u",
            password="a;b",
        )
        assert "PWD={a;b}" in _build_connection_string(c)

    def test_password_with_brace_doubled(self) -> None:
        c = ConnectionConfig(
            backend="mssql",
            host="h",
            port=1433,
            database="d",
            username="u",
            password="a}b",
        )
        assert "PWD={a}}b}" in _build_connection_string(c)

    def test_encrypt_false(self) -> None:
        c = ConnectionConfig(
            backend="mssql",
            host="h",
            port=1433,
            database="d",
            trusted_connection=True,
            encrypt=False,
        )
        assert "Encrypt=no" in _build_connection_string(c)

    def test_trust_server_certificate_true(self) -> None:
        c = ConnectionConfig(
            backend="mssql",
            host="h",
            port=1433,
            database="d",
            trusted_connection=True,
            trust_server_certificate=True,
        )
        assert "TrustServerCertificate=yes" in _build_connection_string(c)

    def test_driver_wrapped_in_braces(self) -> None:
        c = ConnectionConfig(
            backend="mssql",
            host="h",
            port=1433,
            database="d",
            trusted_connection=True,
            driver="ODBC Driver 18 for SQL Server",
        )
        assert "Driver={ODBC Driver 18 for SQL Server}" in _build_connection_string(c)

    def test_no_trailing_semicolon(self) -> None:
        c = ConnectionConfig(
            backend="mssql",
            host="h",
            port=1433,
            database="d",
            trusted_connection=True,
        )
        assert not _build_connection_string(c).endswith(";")

    def test_database_with_semicolon_escaped(self) -> None:
        c = ConnectionConfig(
            backend="mssql",
            host="h",
            port=1433,
            database="db;weird",
            trusted_connection=True,
        )
        assert "Database={db;weird}" in _build_connection_string(c)


class TestLifecycle:
    """Lifecycle tests: connect, close, idempotency, context manager."""

    def test_connect_lazy_no_call_at_init(self, fake_pyodbc: Any) -> None:
        MSSQLBackend(_cfg())
        fake_pyodbc.connect.assert_not_called()

    def test_connect_idempotent(self, fake_pyodbc: Any) -> None:
        b = MSSQLBackend(_cfg())
        b.connect()
        b.connect()
        assert fake_pyodbc.connect.call_count == 1

    def test_close_idempotent(self, fake_pyodbc: Any) -> None:
        b = MSSQLBackend(_cfg())
        b.connect()
        b.close()
        b.close()

    def test_post_close_raises_runtimeerror(self, fake_pyodbc: Any) -> None:
        b = MSSQLBackend(_cfg())
        b.connect()
        b.close()
        with pytest.raises(RuntimeError, match="closed"):
            b.execute_query("SELECT 1")

    def test_context_manager_closes(self, fake_pyodbc: Any) -> None:
        with MSSQLBackend(_cfg()) as b:
            b.execute_query("SELECT 1")
        with pytest.raises(RuntimeError):
            b.execute_query("SELECT 1")

    def test_lazy_connect_on_first_call(self, fake_pyodbc: Any) -> None:
        b = MSSQLBackend(_cfg())
        b.execute_query("SELECT 1")
        fake_pyodbc.connect.assert_called_once()


class TestQueries:
    """Query method tests: parameter translation, rowcount, cursor management."""

    def test_execute_query_translates_named_params(self, fake_pyodbc: Any) -> None:
        conn = fake_pyodbc.connect.return_value
        cur = conn.cursor.return_value
        cur.description = [("col",)]
        cur.fetchall.return_value = [("v",)]
        b = MSSQLBackend(_cfg())
        rows = b.execute_query("SELECT col FROM t WHERE x = :x", {"x": 1})
        cur.execute.assert_called_once_with("SELECT col FROM t WHERE x = ?", [1])
        assert rows == [{"col": "v"}]

    def test_execute_update_returns_rowcount(self, fake_pyodbc: Any) -> None:
        cur = fake_pyodbc.connect.return_value.cursor.return_value
        cur.rowcount = 3
        b = MSSQLBackend(_cfg())
        assert b.execute_update("UPDATE t SET x=:x", {"x": 1}) == 3

    def test_execute_query_no_params_no_placeholders(self, fake_pyodbc: Any) -> None:
        conn = fake_pyodbc.connect.return_value
        cur = conn.cursor.return_value
        cur.description = [("one",)]
        cur.fetchall.return_value = [(1,)]
        b = MSSQLBackend(_cfg())
        rows = b.execute_query("SELECT 1")
        assert rows == [{"one": 1}]

    def test_execute_query_placeholders_but_none_params_raises(
        self, fake_pyodbc: Any
    ) -> None:
        b = MSSQLBackend(_cfg())
        with pytest.raises(KeyError, match="x"):
            b.execute_query("SELECT :x", None)

    def test_autocommit_passed_to_pyodbc(self, fake_pyodbc: Any) -> None:
        MSSQLBackend(_cfg()).connect()
        kwargs = fake_pyodbc.connect.call_args.kwargs
        assert kwargs.get("autocommit") is True

    def test_cursor_closed_after_call(self, fake_pyodbc: Any) -> None:
        cur = fake_pyodbc.connect.return_value.cursor.return_value
        b = MSSQLBackend(_cfg())
        b.execute_query("SELECT 1")
        cur.close.assert_called()

    def test_explain_wraps_with_showplan(self, fake_pyodbc: Any) -> None:
        cur = fake_pyodbc.connect.return_value.cursor.return_value
        cur.fetchall.return_value = [("plan-line",)]
        b = MSSQLBackend(_cfg())
        plan = b.explain("SELECT :a", {"a": 1})
        executed = [c.args[0] for c in cur.execute.call_args_list]
        assert executed[0] == "SET SHOWPLAN_TEXT ON"
        assert "?" in executed[1]
        assert executed[-1] == "SET SHOWPLAN_TEXT OFF"
        assert plan == "plan-line"

    def test_explain_resets_showplan_on_error(self, fake_pyodbc: Any) -> None:
        cur = fake_pyodbc.connect.return_value.cursor.return_value
        cur.execute.side_effect = [None, RuntimeError("boom"), None]
        b = MSSQLBackend(_cfg())
        with pytest.raises(RuntimeError):
            b.explain("SELECT 1")
        executed = [c.args[0] for c in cur.execute.call_args_list]
        assert executed[-1] == "SET SHOWPLAN_TEXT OFF"


class TestConcurrency:
    """Thread-safety tests for lazy-connect."""

    def test_concurrent_connect_calls_pyodbc_once(self, fake_pyodbc: Any) -> None:
        b = MSSQLBackend(_cfg())
        barrier = threading.Barrier(5)

        def worker() -> None:
            barrier.wait()
            b.connect()

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert fake_pyodbc.connect.call_count == 1


class TestErrorSanitization:
    """Tests that the password is redacted in errors from pyodbc.connect."""

    def test_password_redacted_in_pyodbc_error(self, fake_pyodbc: Any) -> None:
        fake_pyodbc.connect.side_effect = fake_pyodbc.Error(
            "login failed for PWD=supersecret"
        )
        b = MSSQLBackend(_cfg(password="supersecret"))
        with pytest.raises(fake_pyodbc.Error) as exc:
            b.connect()
        assert "supersecret" not in str(exc.value)
        assert "***" in str(exc.value)
