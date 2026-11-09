# Step 5 – Batched read on the backends

## LLM prompt
Read `pr_info/steps/summary.md` (sections 2 and 3) and this file. Implement
step 5 only, test-first: add the concrete generator
`DatabaseBackend.iter_readonly_batches` (default chunks
`execute_readonly_query`) and `fetchmany` overrides in the SQLite and SQL Server
backends that close cursor/connection on early exit. No tool uses it yet. Run
pylint, pytest (`-n auto`), mypy; format; one commit.

## WHERE
- `src/mcp_tools_sql/backends/base.py`
- `src/mcp_tools_sql/backends/sqlite.py`
- `src/mcp_tools_sql/backends/mssql.py`
- Tests: `tests/backends/test_batched_read.py` (new)

## WHAT
```python
# base.py
FETCH_BATCH_SIZE: int = 500

class DatabaseBackend(ABC):
    def iter_readonly_batches(
        self,
        sql: str,
        params: dict[str, Any] | None = None,
        *,
        counting: Deadline | None = None,
    ) -> Iterator[list[dict[str, Any]]]:
        """Yield read-only result rows in batches (same guarantee as execute_readonly_query)."""
```

## HOW
- Base default: ignores `counting`; runs `execute_readonly_query` and yields
  slices of `FETCH_BATCH_SIZE`. Not abstract.
- SQLite override: fresh `PRAGMA query_only = ON` connection exactly like
  `execute_readonly_query`; arm `_statement_deadline(conn, seconds, counting)`
  around execute + the whole fetch loop; `finally: cursor.close(); conn.close()`.
- SQL Server override: `_ensure_connected()` first; then `cursor`, and inside
  `with self._timeouts():` execute and the fetch loop; `finally: cursor.close()`.
  `counting` is ignored (the caller checks the clock between batches).
- Callers must close the generator on early stop (`gen.close()` or a
  `contextlib.closing`), which runs the backends' `finally`.
- Docstring: after a timeout/interrupt the generator raises
  `QueryTimeoutError`; never continue fetching after it (on SQLite a later
  `fetchmany` returns `[]`, indistinguishable from end of data).

## ALGORITHM
```
# SQLite
conn = fresh query_only connection
try:
    with _statement_deadline(conn, seconds, counting):
        cur = conn.execute(sql, params or {})
        while batch := cur.fetchmany(FETCH_BATCH_SIZE): yield [dict(r) for r in batch]
finally: close cursor (if created) and conn
```

## DATA
Yields `list[dict[str, Any]]`, each of length ≤ `FETCH_BATCH_SIZE`, never empty.

## Tests (write first)
`tests/backends/test_batched_read.py`:
- Base default: a minimal fake subclass returning 1,201 rows yields batches of
  500/500/201.
- SQLite: a table with 1,201 rows → same batch sizes; rows are dicts.
- SQLite: `gen.close()` after the first batch closes the fresh connection
  (monkeypatch `sqlite3.connect` in the module to record the connection, then
  assert `conn.execute("SELECT 1")` raises `sqlite3.ProgrammingError`).
- SQLite: slow recursive CTE with `query_timeout_seconds=1` → first batch is
  yielded, a later `next()` raises `QueryTimeoutError` (timeout during fetch).
- SQLite: `Deadline` set to `monotonic()` after the first batch → next `next()`
  raises `QueryTimeoutError` well before the statement timeout (mid-batch stop).
- SQL Server (`fake_pyodbc`): `cursor.fetchmany.side_effect = [[r1, r2], [r3], []]`
  → two batches; `gen.close()` after the first batch → `cursor.close` called;
  `fetchmany` raising `OperationalError("HYT00", ...)` → `QueryTimeoutError`.
  Always configure `fetchmany` on the mock (an unconfigured MagicMock never
  returns an empty batch).
