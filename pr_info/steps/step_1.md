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
- **Fast path (no lock)**: if `self._connection is not None` and `not self._closed`,
  return immediately. This keeps the steady-state hot path (every `execute_query`
  call after the first) lock-free.
- Otherwise, acquire `self._connect_lock` (double-checked locking) and inside the
  locked region:
  - Raise `RuntimeError("Backend has been closed.")` if `self._closed`.
  - Re-check `self._connection is not None` and early-return if so.
  - Raise `ValueError` for empty `config.path`.
  - Open `sqlite3.connect(path, check_same_thread=False)` and assign to
    `self._connection`; set `row_factory = sqlite3.Row`.

`SQLiteBackend.close(self) -> None`
- Closes the connection if open, sets `_connection = None`, sets `_closed = True`.
- Remains idempotent.

`SQLiteBackend.execute_query`, `execute_update`, `explain`
- Each calls `self.connect()` at the top, then proceeds as today.
- Drop the `_require_connection()` helper. Each public method calls
  `self.connect()` and then `assert self._connection is not None` to satisfy mypy.

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
    if _connection is not None and not _closed: return  # fast path, no lock
    with _connect_lock:
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

1. **Replace `test_operations_before_connect`** with a parametrized test that
   matches the existing parametrization (`_DATA_METHODS`, which covers
   `execute_query`, `execute_update`, `explain`). Asserts each method
   lazy-connects on first call:
   ```python
   @pytest.mark.parametrize("method,args", [
       ("execute_query", ("SELECT name FROM sqlite_master WHERE type='table'",)),
       ("execute_update", ("UPDATE customers SET name=name WHERE id=-1",)),
       ("explain", ("SELECT 1",)),
   ])
   def test_lazy_connect_on_first_call(
       self, sqlite_db: Path, method: str, args: tuple[Any, ...]
   ) -> None:
       backend = _make_backend(str(sqlite_db))
       getattr(backend, method)(*args)
       assert backend._connection is not None  # connected lazily
       backend.close()
   ```
   No explicit `backend.connect()` call. Adjust the parametrization to reuse the
   file's existing `_DATA_METHODS` constant if present (read
   `tests/backends/test_sqlite.py` first to confirm the helper / fixture names
   actually used: `_make_backend`, `sqlite_db`, `_DATA_METHODS`).

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
