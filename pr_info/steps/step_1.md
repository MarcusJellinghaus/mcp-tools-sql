# Step 1 — Backend read-only describe method

**Goal:** add one `DatabaseBackend` method that returns rows **plus** ordered column names
under the existing read-only guarantee. Sole consumer (from step 3) is the value probe,
which needs per-ordinal values and needs to see duplicate column names that
`dict(zip(...))` would collapse.

**Depends on:** nothing. **Blocks:** step 3.

---

## WHERE

| File | Change |
|---|---|
| `src/mcp_tools_sql/backends/base.py` | New abstract method on `DatabaseBackend` |
| `src/mcp_tools_sql/backends/sqlite.py` | Implementation |
| `src/mcp_tools_sql/backends/mssql.py` | Implementation |
| `tests/backends/test_sqlite.py` | New tests (`sqlite_integration` marker, matching the existing `TestReadOnlyQuery` class) |
| `tests/backends/test_mssql.py` | New tests (fake-pyodbc unit test + `mssql_integration` test) |
| `tests/backends/test_registry.py` | `_FakeBackend` gains the method |
| `tests/test_schema_tools_multitarget.py` | `_FanoutBackend` gains the method |

## WHAT

```python
# backends/base.py — abstract
@abstractmethod
def execute_readonly_query_with_columns(
    self, sql: str, params: dict[str, Any] | None = None
) -> tuple[list[str], list[tuple[Any, ...]]]:
    """Execute a SELECT read-only, returning column names and raw rows."""
```

Same signature in `SQLiteBackend` and `MSSQLBackend`.

## HOW

- Docstring must state the read-only guarantee and mirror the wording style of
  `execute_readonly_query` (SQLite: fresh `PRAGMA query_only = ON` connection; MSSQL:
  documented read-only login). Ruff's `D`/`DOC` rules require `Args:` / `Returns:` /
  `Raises:` sections on `src`.
- SQLite reuses the same fresh-connection pattern as `execute_readonly_query`; it must
  **not** touch `self._connection` and must close in `finally`.
- MSSQL reuses `_ensure_connected()` and `_params_for_pyodbc()`, and closes the cursor in
  `finally`, exactly like `execute_query`.
- Adding an abstract method makes both test doubles fail to instantiate until updated —
  update them in this same commit.
- No `vulture_whitelist.py` entry: the method is called from tests and (later) `source.py`.

## ALGORITHM

```
SQLite:  path = config.path; reject empty
         conn = sqlite3.connect(path); try:
             conn.execute("PRAGMA query_only = ON")
             cur = conn.execute(sql, params or {})
             columns = [d[0] for d in cur.description or ()]
             return (columns, [tuple(r) for r in cur.fetchall()])
         finally: conn.close()

MSSQL:   conn = self._ensure_connected(); sql_q, args = self._params_for_pyodbc(sql, params)
         cur = conn.cursor(); try: cur.execute(sql_q, args)
             columns = [d[0] for d in cur.description or ()]
             return (columns, [tuple(r) for r in cur.fetchall()])
         finally: cur.close()
```

`cursor.description` is `None` for a statement returning no result set, hence `or ()`.

## DATA

`tuple[list[str], list[tuple[Any, ...]]]` — column names in projection order, then one
plain tuple per row, positionally aligned with the names. Rows are **not** dicts: dict keys
cannot represent duplicate column names, which is the whole reason this method exists.

## TESTS (write first)

`tests/backends/test_sqlite.py`
1. Returns `(columns, rows)` with names in projection order and rows as tuples.
2. Binds `:name` params.
3. A write is still rejected (`sqlite3.OperationalError`) — the `query_only` backstop holds.
4. The persistent connection is untouched (mirrors the existing
   `test_readonly_uses_fresh_connection` assertion).
5. **Duplicate-name pin:** self-join a table so two output columns share a name; assert
   `len(columns)` equals the projection width and record the exact names returned. This
   test defines the rule step 3 keys on — if SQLite does not produce the `id:1`
   disambiguation the issue reports, step 3 follows this test, not the issue text.
6. Empty path raises `ValueError`.

`tests/backends/test_mssql.py`
7. Fake-pyodbc: given `cursor.description` with a repeated name, both occurrences survive
   in `columns` (contrast with `execute_query`, which collapses them) and the cursor is
   closed.
8. `mssql_integration`: names and row values match `execute_readonly_query` for a simple
   SELECT.

Doubles: `_FakeBackend` returns `([], [])`; `_FanoutBackend` returns its preset rows as
`(list(self._rows[0].keys()), [tuple(r.values()) for r in self._rows])` or `([], [])` when
empty — whichever keeps its existing tests untouched.

## ACCEPTANCE

All three MCP checks green; `mypy --strict` clean on `src` and `tests`; no behaviour change
to any existing method.

## LLM PROMPT

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_1.md`.
>
> Implement step 1 only, test-first: add the abstract
> `execute_readonly_query_with_columns` to `DatabaseBackend`, implement it in
> `SQLiteBackend` and `MSSQLBackend`, and update the `_FakeBackend` and `_FanoutBackend`
> test doubles so they still instantiate.
>
> Write the tests listed under TESTS before the implementation. Test 5 is a *pin*: run it,
> observe SQLite's real duplicate-column naming, and assert exactly what it does — do not
> assume the `id:1` form.
>
> Use MCP tools for all file and check operations. When done, run
> `mcp__tools-py__run_pylint_check`, `mcp__tools-py__run_pytest_check`
> (`extra_args=["-n", "auto"]`), and `mcp__tools-py__run_mypy_check`, and fix everything
> they report. Do not start step 2.
