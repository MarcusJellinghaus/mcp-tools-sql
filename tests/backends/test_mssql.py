"""Unit tests for the MSSQL backend.

Connection-string and redaction-helper tests live in
``test_mssql_connection_string.py``.
"""

from __future__ import annotations

import threading
from typing import Any
from unittest.mock import MagicMock

import pytest

from mcp_tools_sql.backends.mssql import MSSQLBackend, _odbc_escape
from tests.backends.conftest import LEAKY_PASSWORDS, _cfg, assert_no_leak
from tests.conftest import MSSQLTestEnv


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

    def test_execute_query_preserves_bracket_quoting(self, fake_pyodbc: Any) -> None:
        # T-SQL bracket-quoted identifiers must survive the ``:name`` -> ``?``
        # translation intact: the tsql dialect keeps ``[id]`` as ``[id]`` rather
        # than corrupting it into ``ARRAY(id)``.
        conn = fake_pyodbc.connect.return_value
        cur = conn.cursor.return_value
        cur.description = [("id",)]
        cur.fetchall.return_value = [(1,)]
        b = MSSQLBackend(_cfg())
        b.execute_query("SELECT [id] FROM [orders] WHERE [id] = :id", {"id": 1})
        translated_sql = cur.execute.call_args.args[0]
        assert "[id]" in translated_sql
        assert "[orders]" in translated_sql
        assert "ARRAY(" not in translated_sql
        assert translated_sql.endswith("?")
        assert cur.execute.call_args.args[1] == [1]

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

    def test_execute_readonly_query_delegates(self, fake_pyodbc: Any) -> None:
        """execute_readonly_query is a trivial delegate to execute_query."""
        conn = fake_pyodbc.connect.return_value
        cur = conn.cursor.return_value
        cur.description = [("col",)]
        cur.fetchall.return_value = [("v",)]
        b = MSSQLBackend(_cfg())
        rows = b.execute_readonly_query("SELECT col FROM t WHERE x = :x", {"x": 1})
        cur.execute.assert_called_once_with("SELECT col FROM t WHERE x = ?", [1])
        assert rows == [{"col": "v"}]

    def test_readonly_with_columns_keeps_duplicate_names(
        self, fake_pyodbc: Any
    ) -> None:
        """Repeated names survive; execute_query collapses them into one key."""
        conn = fake_pyodbc.connect.return_value
        cur = conn.cursor.return_value
        cur.description = [("id",), ("name",), ("id",), ("city",)]
        cur.fetchall.return_value = [(1, "Bank A", 1, "Berlin")]
        b = MSSQLBackend(_cfg())
        columns, rows = b.execute_readonly_query_with_columns(
            "SELECT a.id, a.name, b.id, b.city FROM t a JOIN t b ON a.id = b.id"
        )
        assert columns == ["id", "name", "id", "city"]
        assert rows == [(1, "Bank A", 1, "Berlin")]
        # The dict form loses the repeated ``id`` column.
        assert len(b.execute_query("SELECT 1")[0]) == 3
        cur.close.assert_called()

    def test_readonly_with_columns_translates_named_params(
        self, fake_pyodbc: Any
    ) -> None:
        conn = fake_pyodbc.connect.return_value
        cur = conn.cursor.return_value
        cur.description = [("col",)]
        cur.fetchall.return_value = [("v",)]
        b = MSSQLBackend(_cfg())
        columns, rows = b.execute_readonly_query_with_columns(
            "SELECT col FROM t WHERE x = :x", {"x": 1}
        )
        cur.execute.assert_called_once_with("SELECT col FROM t WHERE x = ?", [1])
        assert (columns, rows) == (["col"], [("v",)])

    def test_readonly_with_columns_no_result_set(self, fake_pyodbc: Any) -> None:
        """``cursor.description is None`` → empty column list, no crash."""
        conn = fake_pyodbc.connect.return_value
        cur = conn.cursor.return_value
        cur.description = None
        cur.fetchall.return_value = []
        b = MSSQLBackend(_cfg())
        assert b.execute_readonly_query_with_columns("SELECT 1") == ([], [])

    def test_readonly_with_columns_closes_cursor_on_error(
        self, fake_pyodbc: Any
    ) -> None:
        cur = fake_pyodbc.connect.return_value.cursor.return_value
        cur.execute.side_effect = RuntimeError("boom")
        b = MSSQLBackend(_cfg())
        with pytest.raises(RuntimeError, match="boom"):
            b.execute_readonly_query_with_columns("SELECT 1")
        cur.close.assert_called_once()

    def test_explain_wraps_with_showplan(self, fake_pyodbc: Any) -> None:
        cur = fake_pyodbc.connect.return_value.cursor.return_value
        cur.fetchall.return_value = [("plan-line",)]
        b = MSSQLBackend(_cfg())
        plan = b.explain("SELECT :a", {"a": 1})
        executed = [c.args[0] for c in cur.execute.call_args_list]
        assert executed[0] == "SET SHOWPLAN_TEXT ON"
        assert executed[1] == "SELECT 1"  # literal substituted, no ?
        # cursor.execute is called with no positional args beyond the SQL:
        assert cur.execute.call_args_list[1].args == ("SELECT 1",)
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


class TestIsolatedConnection:
    """Tests for ``MSSQLBackend.get_isolated_connection``."""

    def test_yields_fresh_connection_and_closes(self, fake_pyodbc: Any) -> None:
        fresh_conn = MagicMock(name="fresh_connection")
        fake_pyodbc.connect.return_value = fresh_conn
        b = MSSQLBackend(_cfg())
        with b.get_isolated_connection() as conn:
            assert conn is fresh_conn
            fresh_conn.close.assert_not_called()
        fresh_conn.close.assert_called_once()

    def test_closes_on_exception(self, fake_pyodbc: Any) -> None:
        fresh_conn = MagicMock(name="fresh_connection")
        fake_pyodbc.connect.return_value = fresh_conn
        b = MSSQLBackend(_cfg())
        with pytest.raises(RuntimeError, match="boom"):
            with b.get_isolated_connection():
                raise RuntimeError("boom")
        fresh_conn.close.assert_called_once()

    def test_autocommit_passed_for_isolated_connection(self, fake_pyodbc: Any) -> None:
        b = MSSQLBackend(_cfg())
        with b.get_isolated_connection():
            pass
        kwargs = fake_pyodbc.connect.call_args.kwargs
        assert kwargs.get("autocommit") is True

    @pytest.mark.parametrize("password", LEAKY_PASSWORDS)
    def test_password_redacted_in_connect_error(
        self, fake_pyodbc: Any, password: str
    ) -> None:
        """A failing isolated connect redacts the password like connect() does."""
        fake_pyodbc.connect.side_effect = fake_pyodbc.OperationalError(
            "08001", f"Login failed; PWD={_odbc_escape(password)}"
        )
        b = MSSQLBackend(_cfg(password=password))
        with pytest.raises(fake_pyodbc.Error) as exc:
            with b.get_isolated_connection():
                pass
        assert_no_leak(str(exc.value), password)
        assert "***" in str(exc.value)


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

    @pytest.mark.parametrize("password", LEAKY_PASSWORDS)
    def test_password_redacted_in_pyodbc_error(
        self, fake_pyodbc: Any, password: str
    ) -> None:
        original = fake_pyodbc.OperationalError(
            "08001", f"Login failed; PWD={_odbc_escape(password)}"
        )
        fake_pyodbc.connect.side_effect = original
        b = MSSQLBackend(_cfg(password=password))
        with pytest.raises(fake_pyodbc.Error) as exc:
            b.connect()
        # Secret removed, marker present.
        assert_no_leak(str(exc.value), password)
        assert "***" in str(exc.value)
        # Same instance re-raised: preserves type and sqlstate tuple shape.
        assert exc.value is original
        assert isinstance(exc.value, fake_pyodbc.OperationalError)
        assert exc.value.args[0] == "08001"


class TestConnectDebugLogging:
    """Tests that MSSQLBackend.connect() emits diagnostic debug logs."""

    @pytest.mark.parametrize("password", LEAKY_PASSWORDS)
    def test_connect_logs_redacted_conn_string(
        self, fake_pyodbc: Any, caplog: pytest.LogCaptureFixture, password: str
    ) -> None:
        """Successful connect → debug log contains the redacted conn string."""
        del fake_pyodbc  # only needed for module patching side effect
        b = MSSQLBackend(_cfg(password=password))
        with caplog.at_level("DEBUG", logger="mcp_tools_sql.backends.mssql"):
            b.connect()
        attempt_lines = [
            r.getMessage()
            for r in caplog.records
            if "MSSQL connect attempt" in r.getMessage()
        ]
        assert attempt_lines, "no attempt debug line emitted"
        for line in attempt_lines:
            assert_no_leak(line, password)
            assert "PWD=***" in line

    @pytest.mark.parametrize("password", ["supersecret", "a}b"])
    def test_connect_failure_logs_exception_details(
        self, fake_pyodbc: Any, caplog: pytest.LogCaptureFixture, password: str
    ) -> None:
        """pyodbc.connect raises → debug log records exception type + args."""
        fake_pyodbc.connect.side_effect = fake_pyodbc.OperationalError(
            "08001", f"Login failed; PWD={_odbc_escape(password)}"
        )
        b = MSSQLBackend(_cfg(password=password))
        with caplog.at_level("DEBUG", logger="mcp_tools_sql.backends.mssql"):
            with pytest.raises(fake_pyodbc.Error):
                b.connect()
        failure_lines = [
            r.getMessage()
            for r in caplog.records
            if "MSSQL connect failed" in r.getMessage()
        ]
        assert failure_lines, "no failure debug line emitted"
        for line in failure_lines:
            assert "OperationalError" in line
            assert "08001" in line
            assert_no_leak(line, password)


@pytest.mark.mssql_integration
class TestMSSQLIntegration:
    """Round-trip tests against a real SQL Server.

    Skipped automatically when ``TEST_MSSQL_*`` env vars are missing
    (handled by the ``mssql_db`` fixture).
    """

    def test_execute_query_real_round_trip(self, mssql_db: MSSQLTestEnv) -> None:
        with MSSQLBackend(mssql_db.config) as b:
            rows = b.execute_query(
                f"SELECT name FROM {mssql_db.schema}.customers "
                "WHERE country = :country",
                {"country": "Germany"},
            )
        assert rows == [{"name": "Bank A"}]

    def test_execute_update_real_round_trip(self, mssql_db: MSSQLTestEnv) -> None:
        with MSSQLBackend(mssql_db.config) as b:
            n = b.execute_update(
                f"INSERT INTO {mssql_db.schema}.customers "
                "VALUES (:id, :name, :country)",
                {"id": 99, "name": "Bank Z", "country": "Spain"},
            )
        assert n == 1

    def test_execute_readonly_query_delegates(self, mssql_db: MSSQLTestEnv) -> None:
        """execute_readonly_query returns the same rows as execute_query."""
        sql = f"SELECT name FROM {mssql_db.schema}.customers WHERE country = :country"
        with MSSQLBackend(mssql_db.config) as b:
            ro_rows = b.execute_readonly_query(sql, {"country": "Germany"})
            rw_rows = b.execute_query(sql, {"country": "Germany"})
        assert ro_rows == rw_rows == [{"name": "Bank A"}]

    def test_readonly_with_columns_matches_dict_form(
        self, mssql_db: MSSQLTestEnv
    ) -> None:
        """Names and values agree with execute_readonly_query's dict rows."""
        sql = f"SELECT id, name FROM {mssql_db.schema}.customers ORDER BY id"
        with MSSQLBackend(mssql_db.config) as b:
            columns, rows = b.execute_readonly_query_with_columns(sql)
            dict_rows = b.execute_readonly_query(sql)
        assert columns == ["id", "name"]
        assert rows == [(1, "Bank A"), (2, "Bank B")]
        assert [dict(zip(columns, row)) for row in rows] == dict_rows

    def test_readonly_with_columns_keeps_duplicate_names(
        self, mssql_db: MSSQLTestEnv
    ) -> None:
        """A real self-join keeps one entry per projected column."""
        sql = (
            "SELECT a.id, a.name, b.id, b.country "
            f"FROM {mssql_db.schema}.customers a "
            f"JOIN {mssql_db.schema}.customers b ON a.id = b.id "
            "ORDER BY a.id"
        )
        with MSSQLBackend(mssql_db.config) as b:
            columns, rows = b.execute_readonly_query_with_columns(sql)
        assert len(columns) == 4
        assert rows[0] == (1, "Bank A", 1, "Germany")

    def test_describe_columns_resolves_a_join(self, mssql_db: MSSQLTestEnv) -> None:
        """``sys.dm_exec_describe_first_result_set`` types a real join.

        The one check the ``MagicMock`` unit tests cannot make: that
        ``DMF_SQL`` executes as written on a live server and reports the
        seeded columns' exact ``system_type_name`` -- without executing the
        join. The fixture uses a schema-creating login, so this does **not**
        establish that the shipping read-only login may run the DMF; that is
        the separately verified prerequisite behind the probe fallback.
        """
        from mcp_tools_sql.summarize.source import describe_columns, validate_source

        ref, _notes, error = validate_source(
            f"SELECT c.name AS customer, o.total AS order_total "
            f"FROM {mssql_db.schema}.customers c "
            f"JOIN {mssql_db.schema}.orders o ON c.id = o.customer_id",
            None,
            "tsql",
        )
        assert error is None
        assert ref is not None

        with MSSQLBackend(mssql_db.config) as b:
            metas, reason = describe_columns(b, ref, None)

        assert reason is None
        assert metas is not None
        assert [m.name for m in metas] == ["customer", "order_total"]
        assert [m.declared_type for m in metas] == ["nvarchar(50)", "float"]
        assert [m.category for m in metas] == ["string", "numeric"]

    def test_explain_returns_text_plan(self, mssql_db: MSSQLTestEnv) -> None:
        with MSSQLBackend(mssql_db.config) as b:
            plan = b.explain(
                f"SELECT * FROM {mssql_db.schema}.customers WHERE id = :id",
                {"id": 1},
            )
        assert isinstance(plan, str)
        assert len(plan) > 0

    def test_connect_close_lifecycle(self, mssql_db: MSSQLTestEnv) -> None:
        b = MSSQLBackend(mssql_db.config)
        b.connect()
        b.connect()
        b.execute_query("SELECT 1 AS one")
        b.close()
        b.close()
        with pytest.raises(RuntimeError):
            b.execute_query("SELECT 1")

    def test_isolated_connection_round_trip(self, mssql_db: MSSQLTestEnv) -> None:
        with MSSQLBackend(mssql_db.config) as b:
            with b.get_isolated_connection() as conn:
                cursor = conn.cursor()
                try:
                    cursor.execute("SELECT 1")
                    row = cursor.fetchone()
                finally:
                    cursor.close()
            assert tuple(row) == (1,)

    def test_isolated_connection_does_not_affect_persistent(
        self, mssql_db: MSSQLTestEnv
    ) -> None:
        with MSSQLBackend(mssql_db.config) as b:
            with b.get_isolated_connection():
                pass
            rows = b.execute_query("SELECT 1 AS x")
        assert rows == [{"x": 1}]
