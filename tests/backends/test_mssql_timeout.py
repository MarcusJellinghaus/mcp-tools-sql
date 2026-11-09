"""Login/statement timeout tests for the MSSQL backend."""

from __future__ import annotations

import itertools
from typing import Any

import pytest

from mcp_tools_sql.backends.base import (
    BackendConnectionError,
    Deadline,
    QueryTimeoutError,
)
from mcp_tools_sql.backends.mssql import MSSQLBackend
from mcp_tools_sql.config.models import LimitsConfig
from mcp_tools_sql.result_limits import Source, collect
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
        with pytest.raises(BackendConnectionError) as info:
            b.execute_query("SELECT 1")
        assert info.value.__cause__ is err
        assert info.value.args == ("42000", "syntax error")

    def test_login_hyt00_not_translated(self, fake_pyodbc: Any) -> None:
        fake_pyodbc.connect.side_effect = fake_pyodbc.OperationalError(
            "HYT00", "login timeout"
        )
        b = MSSQLBackend(_cfg())
        with pytest.raises(BackendConnectionError) as info:
            b.execute_query("SELECT 1")
        assert not isinstance(info.value, QueryTimeoutError)
        assert info.value.args[0] == "HYT00"

    def test_isolated_login_hyt00_not_translated(self, fake_pyodbc: Any) -> None:
        fake_pyodbc.connect.side_effect = fake_pyodbc.OperationalError(
            "HYT00", "login timeout"
        )
        b = MSSQLBackend(_cfg())
        with pytest.raises(BackendConnectionError):
            with b.get_isolated_connection():
                pass


class TestBatchedReadCancel:
    """An early close cancels the statement before closing the cursor."""

    @staticmethod
    def _cursor(fake_pyodbc: Any, batches: list[list[tuple[Any, ...]]]) -> Any:
        cur = fake_pyodbc.connect.return_value.cursor.return_value
        cur.description = [("id",)]
        cur.fetchmany.side_effect = [*batches, []]
        return cur

    @staticmethod
    def _lifecycle(cur: Any) -> list[str]:
        return [c[0] for c in cur.method_calls if c[0] in ("cancel", "close")]

    @staticmethod
    def _collect(backend: MSSQLBackend, max_rows: int) -> Any:
        def _open(dl: Deadline) -> Any:
            return backend.iter_readonly_batches("SELECT id FROM t", counting=dl)

        return collect(
            [Source("d", _open)],
            max_rows=max_rows,
            limits=LimitsConfig(max_count_rows=100),
            counting_seconds=5.0,
        )

    def test_generator_closed_early(self, fake_pyodbc: Any) -> None:
        cur = self._cursor(fake_pyodbc, [[(1,)], [(2,)]])
        gen = MSSQLBackend(_cfg()).iter_readonly_batches("SELECT id FROM t")
        assert next(gen) == [{"id": 1}]
        gen.close()
        assert self._lifecycle(cur) == ["cancel", "close"]

    def test_max_count_rows_reached(self, fake_pyodbc: Any) -> None:
        cur = self._cursor(fake_pyodbc, [[(i,) for i in range(101)], [(101,)]])
        result = self._collect(MSSQLBackend(_cfg()), max_rows=10)
        assert result.stop == "max_count"
        assert self._lifecycle(cur) == ["cancel", "close"]

    def test_counting_time_limit_hit(
        self, fake_pyodbc: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        clock = itertools.count(0.0, 100.0)
        monkeypatch.setattr(
            "mcp_tools_sql.result_limits.time.monotonic", lambda: next(clock)
        )
        cur = self._cursor(fake_pyodbc, [[(1,), (2,)], [(3,)]])
        result = self._collect(MSSQLBackend(_cfg()), max_rows=1)
        assert result.stop == "counting"
        assert self._lifecycle(cur) == ["cancel", "close"]

    def test_exhaustion_does_not_cancel(self, fake_pyodbc: Any) -> None:
        cur = self._cursor(fake_pyodbc, [[(1,)], [(2,)]])
        gen = MSSQLBackend(_cfg()).iter_readonly_batches("SELECT id FROM t")
        assert list(gen) == [[{"id": 1}], [{"id": 2}]]
        assert self._lifecycle(cur) == ["close"]

    def test_cancel_failure_still_closes(self, fake_pyodbc: Any) -> None:
        cur = self._cursor(fake_pyodbc, [[(1,)], [(2,)]])
        cur.cancel.side_effect = fake_pyodbc.Error("HY000", "cancel failed")
        gen = MSSQLBackend(_cfg()).iter_readonly_batches("SELECT id FROM t")
        next(gen)
        gen.close()
        cur.close.assert_called_once()
