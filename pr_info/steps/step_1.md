# Step 1 — Backend lazy-connect

## LLM prompt

> Read `pr_info/steps/summary.md` and then implement Step 1 in
> `pr_info/steps/step_1.md`. TDD: update / add tests first, then change the
> backend. Run pylint + pytest + mypy after each edit; all three must pass.
> One commit at the end.

## Goal

`DatabaseBackend.execute_query` / `execute_update` / `explain` lazy-connect on
first call. After `close()`, calling them raises `RuntimeError`. Thread-safe via
`threading.Lock`. `verify` path is untouched.

---

## WHERE

- `src/mcp_tools_sql/backends/base.py` — docstring contract update only.
- `src/mcp_tools_sql/backends/sqlite.py` — implementation.
- `tests/backends/test_sqlite.py` — adjust the two existing tests, add one.

## WHAT

`SQLiteBackend.__init__(self, config: ConnectionConfig) -> None`
- Adds `self._closed: bool = False` and `self._connect_lock = threading.Lock()`.

`SQLiteBackend.connect(self) -> None`
- Acquires `self._connect_lock`.
- Raises `RuntimeError("Backend has been closed.")` if `self._closed`.
- Existing idempotent body (early-return when `_connection is not None`, raise
  `ValueError` for empty path, open `sqlite3.connect(path, check_same_thread=False)`).

`SQLiteBackend.close(self) -> None`
- Closes the connection if open, sets `_connection = None`, sets `_closed = True`.
- Remains idempotent.

`SQLiteBackend.execute_query`, `execute_update`, `explain`
- Each calls `self.connect()` at the top, then proceeds as today.
- Drop the `_require_connection()` helper (or keep it as a thin asserter for mypy).

## HOW

- Module imports: add `import threading` to `sqlite.py`.
- No public-API change: `connect()` and `close()` keep their signatures.
- The contract change is documented in `DatabaseBackend.execute_query` /
  `execute_update` / `explain` docstrings in `base.py`:

  > `execute_query` implies connected — backends MUST connect lazily on first
  > call. After `close()`, further calls raise `RuntimeError`.

## ALGORITHM

```
connect():
    acquire _connect_lock:
        if _closed: raise RuntimeError("Backend has been closed.")
        if _connection is not None: return
        if not config.path: raise ValueError("SQLite path must not be empty.")
        _connection = sqlite3.connect(path, check_same_thread=False)
        _connection.row_factory = sqlite3.Row

execute_query(sql, params):
    self.connect()
    cursor = self._connection.execute(sql, params or {})
    return [dict(row) for row in cursor.fetchall()]
```

(`execute_update` and `explain` follow the same pattern: `self.connect()` at top.)

## DATA

No public return-type changes. Internal additions:
- `self._closed: bool` (default `False`)
- `self._connect_lock: threading.Lock`

---

## Tests (TDD — write first)

In `tests/backends/test_sqlite.py`:

1. **Replace `test_operations_before_connect`** with a test asserting lazy-connect
   succeeds:
   ```python
   def test_lazy_connect_on_first_call(self, sqlite_db: Path) -> None:
       backend = _make_backend(str(sqlite_db))
       rows = backend.execute_query(
           "SELECT name FROM sqlite_master WHERE type='table'"
       )
       assert any(r["name"] == "customers" for r in rows)
       backend.close()
   ```
   No explicit `backend.connect()` call.

2. **Update `test_operations_after_close`** parametrize match string to
   `"Backend has been closed"` (replaces today's `"Not connected"`).

3. **Add a thread-safety smoke test**: spawn 5 threads each calling
   `execute_query("SELECT 1")` on a fresh backend, assert no exception and the
   underlying `sqlite3.Connection` was created exactly once. Use an assertion
   on a counter (mock `sqlite3.connect` via `monkeypatch` to count calls).

4. **`test_connect_empty_path`** still passes — `connect()` still raises
   `ValueError` when `config.path == ""`.

## Acceptance

- `mcp__tools-py__run_pytest_check(extra_args=["-n", "auto", "-m", "not git_integration and not claude_cli_integration and not claude_api_integration and not formatter_integration and not github_integration and not langchain_integration"])` — green.
- `mcp__tools-py__run_pylint_check` — green.
- `mcp__tools-py__run_mypy_check` — green.
- `mcp__tools-py__run_lint_imports_check` — green.
- One commit: `feat(backends): lazy-connect SQLiteBackend with threading.Lock`.
