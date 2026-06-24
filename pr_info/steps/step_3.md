# Step 3 — `execute_readonly_query` backend seam (ABC + SQLite + MSSQL)

> Read `pr_info/steps/summary.md` first. Adds the read-only execution seam used
> by `count_records` (Step 5). Independent of the parser changes — could land in
> parallel, but is sequenced here for a clean history.

## WHERE
- `src/mcp_tools_sql/backends/base.py` (new abstractmethod)
- `src/mcp_tools_sql/backends/sqlite.py` (fresh read-only connection)
- `src/mcp_tools_sql/backends/mssql.py` (delegate)
- `tests/backends/test_sqlite.py`, `tests/backends/test_mssql.py` (tests)

## WHAT
```python
# base.py  (DatabaseBackend ABC)
@abstractmethod
def execute_readonly_query(
    self, sql: str, params: dict[str, Any] | None = None
) -> list[dict[str, Any]]: ...
```
```python
# sqlite.py  — fresh per-call connection, PRAGMA query_only=ON, closed after use
def execute_readonly_query(self, sql, params=None) -> list[dict[str, Any]]: ...
```
```python
# mssql.py  — wrapper + documented read-only login is the model; delegate
def execute_readonly_query(self, sql, params=None) -> list[dict[str, Any]]:
    return self.execute_query(sql, params)
```

## HOW (integration)
- `base.py`: add the `@abstractmethod`; keep docstring describing the asymmetric
  semantics (SQLite fresh `PRAGMA query_only`; MSSQL delegates; Postgres future
  `SET TRANSACTION READ ONLY`).
- `sqlite.py`: open a brand-new `sqlite3.connect(self._config.path,
  check_same_thread=False)`, set `row_factory = sqlite3.Row`,
  `execute("PRAGMA query_only = ON")`, run the query, `close()` in `finally`.
  Do **not** touch the persistent connection. Reuse the empty-path
  `ValueError` guard from `connect()` (read `self._config.path`).

## ALGORITHM (SQLite)
```
path = self._config.path
if not path: raise ValueError("SQLite path must not be empty.")
conn = sqlite3.connect(path, check_same_thread=False)
try:
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")
    cur = conn.execute(sql, params or {})
    return [dict(r) for r in cur.fetchall()]
finally:
    conn.close()
```

## DATA
- Returns `list[dict[str, Any]]` (column-name keyed rows), same shape as
  `execute_query`.

## TDD / TESTS
`tests/backends/test_sqlite.py` (file-based DB, not `:memory:`):
- Returns rows as dicts for a normal `SELECT` (parity with `execute_query`).
- Sees **committed** data written via `execute_update` (separate connection,
  autocommit semantics) — proves the fresh connection reads the file.
- A write through the read-only connection fails (e.g. `INSERT`/`UPDATE` raises
  `sqlite3.OperationalError` — `attempt to write a readonly database` / query_only),
  proving `PRAGMA query_only = ON` is active.
- The persistent connection remains usable afterwards (fresh connection closed,
  backend not affected).

`tests/backends/test_mssql.py` (under `@pytest.mark.mssql_integration`):
- `execute_readonly_query` returns the same rows as `execute_query` for a seeded
  SELECT (delegation). (CI skips MSSQL; this documents behavior.)

## DONE WHEN
- All three checks pass (unit subset green; MSSQL test is skipped in CI).
- Single commit: base.py + sqlite.py + mssql.py + the two backend test files.

## LLM PROMPT
> Implement Step 3 of `pr_info/steps/summary.md` (`pr_info/steps/step_3.md`).
> Add the `execute_readonly_query` `@abstractmethod` to `DatabaseBackend` in
> `src/mcp_tools_sql/backends/base.py`. Implement it in
> `src/mcp_tools_sql/backends/sqlite.py` as a fresh per-call connection with
> `row_factory = sqlite3.Row` and `PRAGMA query_only = ON`, closed in `finally`,
> never touching the persistent connection; in
> `src/mcp_tools_sql/backends/mssql.py` delegate to `execute_query`. Write the
> TDD tests in `tests/backends/test_sqlite.py` (returns dicts, sees committed
> data, write is rejected, persistent connection still works) and an
> `mssql_integration` delegation test in `tests/backends/test_mssql.py`. Use MCP
> tools only; run pylint, mypy, and the unit pytest subset until green. Produce
> exactly one commit.
