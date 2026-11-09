# Step 8 — SHOWPLAN into `MSSQLBackend.explain(isolated=True)`; drop `get_isolated_connection`

See `pr_info/steps/summary.md` for the overall design.

## Kind
Restructure. TDD: tests first.

## WHERE
- `src/mcp_tools_sql/backends/base.py` — `explain` signature + docstring; remove abstract
  `get_isolated_connection` (and the `AbstractContextManager` import if unused).
- `src/mcp_tools_sql/backends/mssql.py` — rename `get_isolated_connection` → `_isolated_connection`;
  `explain(..., isolated)`; private `_showplan`.
- `src/mcp_tools_sql/backends/sqlite.py` — `explain(..., isolated)` (ignored); delete `get_isolated_connection`.
- `src/mcp_tools_sql/validation_tools.py` — delete `_explain`; call `backend.explain(sql, params, isolated=True)`.
- `vulture_whitelist.py` — remove `_.get_isolated_connection`.
- Tests:
  - new `tests/backends/test_mssql_explain.py` (moved SHOWPLAN tests, using `fake_pyodbc`);
  - `tests/test_validation_tools.py` — remove the three `_explain` MSSQL unit tests (moved);
  - `tests/test_tool_timeouts.py` — fake backend: drop `get_isolated_connection`, add `isolated`
    to `explain`; delete `test_validate_sql_tsql_hyt00_is_timeout`,
    `test_validate_sql_tsql_other_sqlstate_is_not_timeout`, `_tsql_conn` and the `_DriverError`
    stand-in (both cases move to `tests/backends/test_mssql_explain.py`, driven by `fake_pyodbc`);
  - test fakes' `explain` gain `*, isolated: bool = False` and lose `get_isolated_connection`:
    `tests/test_query_limits_tools.py`, `tests/test_schema_tools_fanout_limits.py`,
    `tests/test_schema_tools_multitarget.py`, `tests/backends/test_batched_read.py`,
    `tests/backends/test_registry.py`;
  - `tests/backends/test_mssql.py`, `tests/backends/test_mssql_timeout.py` — calls to
    `get_isolated_connection()` → `_isolated_connection()` (yield/close/autocommit/redaction,
    real-DB isolated round-trip, isolated login/statement timeouts, untranslated login HYT00);
  - `tests/backends/test_sqlite.py` — delete the `get_isolated_connection` test class.

## WHAT
```python
# base.py
@abstractmethod
def explain(
    self, sql: str, params: dict[str, Any] | None = None, *, isolated: bool = False
) -> str:
    """Return the query execution plan as text.

    isolated: run on a fresh single-use connection where the backend has one
    (MSSQL); backends without one (SQLite) ignore it. Isolated calls skip the
    closed check where the backend opens a fresh connection. ...
    """

# mssql.py
@contextmanager
def _isolated_connection(self) -> Iterator[Any]: ...          # renamed; finally: conn.close() inside self._timeouts()
def explain(self, sql, params=None, *, isolated=False) -> str: ...
def _showplan(self, conn: Any, explain_sql: str) -> str: ...   # SHOWPLAN ON / stmt / OFF
```

## HOW
- MSSQL isolated path: substitute literals **before** opening the connection (non-finite float
  raises `ValueError` with no connect) and do not check `_closed`. Persistent path keeps
  connect-then-substitute.
- `_isolated_connection` is entered **outside** `_timeouts()` (login errors are already neutral,
  login `HYT00` stays a `BackendConnectionError`). Its body changes in one place: the
  `finally: conn.close()` now runs inside `with self._timeouts():` so a close error is translated
  (no raw pyodbc error escapes the backend).
- `validation_tools.py`: remove `_explain`, `translate_timeout`, `substitute_named_with_literals`
  imports that become unused; in `core` use
  `plan = backend.explain(sql, params, isolated=True)`. The timeout comes from the backend's own
  config, which is `target.config` (registry builds the backend from it), so the timeout text is unchanged.
- SQLite `explain` accepts `isolated` and ignores it (persistent connection, as today).
- Run `run_vulture_check`; whitelist `isolated` only if vulture reports it.

## ALGORITHM
```
explain(sql, params=None, *, isolated=False):
    if isolated:
        explain_sql = substitute_named_with_literals(sql, params or {}, "tsql")
        with self._isolated_connection() as conn:
            return self._showplan(conn, explain_sql)
    conn = self._ensure_connected()
    return self._showplan(conn, substitute_named_with_literals(sql, params or {}, "tsql"))

_showplan(conn, explain_sql):
    with self._timeouts():
        cursor = conn.cursor()
        try:
            cursor.execute("SET SHOWPLAN_TEXT ON")
            try: cursor.execute(explain_sql); rows = cursor.fetchall()
            finally: cursor.execute("SET SHOWPLAN_TEXT OFF")
        finally: cursor.close()
    return "\n".join(r[0] for r in rows if r and r[0])
```

## DATA
Plan text identical to today's for both paths.

## Tests first (`tests/backends/test_mssql_explain.py`, `fake_pyodbc`)
- `explain("SELECT :a", {"a": 1}, isolated=True)`: a fresh `fake.connect` call, cursor execute
  sequence `["SET SHOWPLAN_TEXT ON", "SELECT 1", "SET SHOWPLAN_TEXT OFF"]`, the statement call
  has no params argument, cursor and the fresh connection are closed, result
  `"StmtText\nplan-row-1"` (moved from `test_mssql_explain_showplan_sequence`).
- SHOWPLAN OFF still runs when the statement raises; the exception propagates (moved test).
- `explain("SELECT :x", {"x": float("inf")}, isolated=True)` → `ValueError("non-finite")`,
  `fake.connect.assert_not_called()` (retargeted `test_mssql_explain_non_finite_float_raises_value_error`).
- After `close()`, `explain(..., isolated=True)` still works; `explain(...)` (persistent) raises `RuntimeError`.
- Statement `HYT00` during isolated SHOWPLAN → `QueryTimeoutError`; login `HYT00` on the isolated
  connect → `BackendConnectionError` (statement case moved from
  `test_validate_sql_tsql_hyt00_is_timeout`).
- Non-timeout SQLSTATE during isolated SHOWPLAN: statement raising `fake.Error("42000", "driver message")`
  → `BackendError` (not `QueryTimeoutError`), `original_class == "Error"`, `str` equal to the
  original's (moved from `test_validate_sql_tsql_other_sqlstate_is_not_timeout`).
- Isolated connection `close()` raising `fake.Error` → `BackendError` with `original_class == "Error"`.
- SQLite: `explain(sql, params, isolated=True) == explain(sql, params)`.
- `validate_sql` (mock backend) calls `explain` with `isolated=True` on both dialects.

## Verification
- `search_files` for `get_isolated_connection` → no match in `src/`, `tests/`, `vulture_whitelist.py`.
- pylint, pytest (`-n auto`), mypy, vulture, lint-imports, ruff green; format; one commit.

## Commit
`refactor(backends): move SHOWPLAN into MSSQLBackend.explain(isolated=True)`

## LLM prompt
> Read `pr_info/steps/summary.md` and `pr_info/steps/step_8.md`. Write
> `tests/backends/test_mssql_explain.py` first (moving the three MSSQL `_explain` tests out of
> `tests/test_validation_tools.py` and the two T-SQL SHOWPLAN cases out of
> `tests/test_tool_timeouts.py`, deleting `_DriverError` there). Then add `isolated` to `DatabaseBackend.explain`, implement
> it in MSSQL via `_isolated_connection()` + `_showplan()`, accept-and-ignore it in SQLite,
> remove `get_isolated_connection` everywhere (ABC, SQLite, test fakes, vulture whitelist), and
> make `validation_tools` call `backend.explain(sql, params, isolated=True)`. Retarget the MSSQL
> isolated-connection tests to `_isolated_connection()` and delete the SQLite ones. Use MCP tools
> only. Run pylint, pytest (`-n auto`), mypy, vulture, lint-imports and ruff; all must pass.
> Format, then one commit.
