# Step 4 — Replace backend connection asserts with explicit checks

## LLM prompt
> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_4.md`.
> Do not change `pyproject.toml`. Run the checks listed below, format, and
> make exactly one commit.

## WHERE
- `src/mcp_tools_sql/backends/sqlite.py` — class `SQLiteBackend`
- `src/mcp_tools_sql/backends/mssql.py` — `MSSQLBackend._ensure_connected`

## WHAT
### SQLite — new private helper
```python
def _require_connection(self) -> sqlite3.Connection:
    """Lazily connect and return the live connection.

    Returns:
        The open SQLite connection.

    Raises:
        RuntimeError: If no connection is open after ``connect()``.
    """
```
Place it directly after `close()`.

Callers (each loses `self.connect()` + `assert self._connection is not None`):
- `execute_query`: `cursor = self._require_connection().execute(sql, params or {})`
- `execute_update`: `conn = self._require_connection()`; use `conn.execute(...)`
  and `conn.commit()`.
- `explain`: `cursor = self._require_connection().execute(f"EXPLAIN QUERY PLAN {sql}", params or {})`
- `get_isolated_connection`: `yield self._require_connection()`

Docstrings of these four public methods stay unchanged.

### MSSQL — existing helper
In `_ensure_connected`, replace `assert self._connection is not None` with the
raise below and add a `Raises:` section to its docstring:
```
Raises:
    RuntimeError: If no connection is open after ``connect()``.
```

## ALGORITHM (both helpers)
```
self.connect()                      # may already raise "Backend has been closed."
if self._connection is None:
    msg = "Backend connection is not open."
    raise RuntimeError(msg)
return self._connection
```
(Use the `msg = ...; raise X(msg)` idiom already used in both files.)

## HOW
TDD: the raise is unreachable (`connect()` either sets `_connection` or
raises), so per the issue no new test is added. Existing
`tests/backends/test_sqlite.py` (including the closed-backend parametrized
test that expects `"Backend has been closed"`) and `test_mssql.py` cover the
behaviour.

## DATA
`_require_connection` returns `sqlite3.Connection`; `_ensure_connected` keeps
returning `Any`.

## Verification
- `run_ruff_check(select=["S101"], target_directories=["src/mcp_tools_sql/backends"])` → clean.
- `run_ruff_check(target_directories=["src","tests","tools"])` → clean
  (`DOC501` is satisfied by the `Raises:` sections).
- mypy `--strict` green (no `unreachable` warning: `_connection` is typed
  `Optional` / `Any`).
- pylint, full pytest green.

## Commit
`backends: replace connection asserts with explicit RuntimeError`
