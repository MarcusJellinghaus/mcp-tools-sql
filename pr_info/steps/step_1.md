# Step 1 — Backend isolation primitive

Add `DatabaseBackend.get_isolated_connection()` as a context-manager primitive on the backend abstract base, with SQLite (no-op) and MSSQL (fresh connection) implementations. Pure backend work — no validation logic, no MCP wiring.

## WHERE

- `src/mcp_tools_sql/backends/base.py` — abstract method declaration.
- `src/mcp_tools_sql/backends/sqlite.py` — no-op implementation.
- `src/mcp_tools_sql/backends/mssql.py` — fresh-connection implementation.
- `tests/backends/test_sqlite.py` — SQLite isolation tests.
- `tests/backends/test_mssql.py` — MSSQL isolation tests (mocked unit + `mssql_integration`).

## WHAT

### `DatabaseBackend.get_isolated_connection`
```python
@abstractmethod
def get_isolated_connection(self) -> AbstractContextManager[Any]:
    """Yield a single-use connection.

    SQLite yields the persistent connection (no-op isolation: EXPLAIN QUERY
    PLAN does not execute the statement). MSSQL yields a fresh pyodbc
    connection built from the same ConnectionConfig, closed on context exit.
    Callers MUST NOT close the yielded connection; the backend owns its
    lifecycle.
    """
```

### `SQLiteBackend.get_isolated_connection`
```python
@contextmanager
def get_isolated_connection(self) -> AbstractContextManager[Any]:  # type: ignore[misc]
    self.connect()
    assert self._connection is not None
    yield self._connection
```

### `MSSQLBackend.get_isolated_connection`
```python
@contextmanager
def get_isolated_connection(self) -> AbstractContextManager[Any]:  # type: ignore[misc]
    import pyodbc  # pylint: disable=import-error,import-outside-toplevel
    conn = pyodbc.connect(_build_connection_string(self._config), autocommit=True)
    try:
        yield conn
    finally:
        conn.close()
```

Note: the public return annotation is `AbstractContextManager[Any]` to match the abstract (Option A in HOW). `@contextmanager` wraps the generator into a `_GeneratorContextManager` (an `AbstractContextManager`); the `type: ignore[misc]` suppresses the mypy complaint about declaring a generator function's return as a non-`Iterator` type.

## HOW

- `base.py`: add `from contextlib import AbstractContextManager` to imports; declare the method as `@abstractmethod`.
- `sqlite.py` and `mssql.py`: add `from contextlib import AbstractContextManager, contextmanager`; decorate each impl with `@contextmanager`. (No `Iterator` import is needed since the public return annotation is `AbstractContextManager[Any]` per Option A.)
- Strict-mypy override-signature note: the abstract method's return type (`AbstractContextManager[Any]`) does not match the `@contextmanager`-decorated impls' generator signature (`Iterator[Any]`) under strict mypy. Resolution (Option A — no existing `@contextmanager` convention in `backends/base.py` to follow): declare the abstract method as a plain method (no `@contextmanager`) returning `AbstractContextManager[Any]`; concrete impls use `@contextmanager` but their public type annotation is also `AbstractContextManager[Any]` (typing the inner generator function's return as `Iterator[Any]` is fine internally). This keeps the override compatible under `--strict`.
- MSSQL impl mirrors the lazy-import pattern already used in `MSSQLBackend.connect()` — `pyodbc` is imported inside the function so the SQLite-only install path stays unbroken.
- No password-redaction wrapping is needed here: errors during `pyodbc.connect` already get the same treatment via the existing redaction logic only on the persistent connection's `connect()`. The isolated path is for validation only; if it fails, the calling tool catches it in the Step 2 exception ladder. Passwords in the connection string are not echoed because pyodbc errors don't include the connection string in their message text by default. (If a future audit reveals leakage, add the same `_sanitize` wrapping then — out of scope here.)

## ALGORITHM

```
SQLite:  ensure connect(), yield persistent _connection, no teardown.
MSSQL:   build conn_str, pyodbc.connect(autocommit=True),
         try: yield conn
         finally: conn.close()  # runs on success and on exception
```

## DATA

- Return: `AbstractContextManager[Any]` (the underlying DB-API connection object — `sqlite3.Connection` or `pyodbc.Connection`).
- No exceptions raised by the primitive itself except those that bubble up from `connect()` / `pyodbc.connect()`.

## Tests

### `tests/backends/test_sqlite.py`
- [ ] `get_isolated_connection` yields the persistent connection: `with backend.get_isolated_connection() as conn: assert conn is backend._connection`.
- [ ] After context exit, the persistent connection is still open and usable (verify by running a `SELECT 1` on `backend` afterwards).
- [ ] Entering the `with` block on a fresh (unconnected) backend triggers lazy `connect()` — i.e. the body of the context manager runs on `__enter__`, not on the bare call.

### `tests/backends/test_mssql.py` — unit (no DB)
- [ ] With `pyodbc.connect` monkeypatched to a `MagicMock`, `get_isolated_connection()` yields the mock and calls `.close()` on context exit. (Use `unittest.mock` against the inline `pyodbc` import — patch `pyodbc.connect` via `monkeypatch.setattr` after importing pyodbc inside the test.)
- [ ] On an exception inside the `with` block, the mock's `.close()` is still called.

### `tests/backends/test_mssql.py` — integration (`@pytest.mark.mssql_integration`)
- [ ] `with backend.get_isolated_connection() as conn:` followed by `cursor = conn.cursor(); cursor.execute("SELECT 1"); cursor.fetchone()` returns `(1,)`.
- [ ] After context exit, `backend.execute_query("SELECT 1 AS x")` on the persistent connection still works (proves the isolated close did not affect the backend's persistent connection).

## Commit & checks

Commit message: `feat(backends): add get_isolated_connection primitive`.

Run before commit:
- `mcp__mcp-tools-py__run_format_code`
- `mcp__mcp-tools-py__run_pytest_check` with `extra_args=["-n", "auto"]`
- `mcp__mcp-tools-py__run_pylint_check`
- `mcp__mcp-tools-py__run_mypy_check`

All must pass.

## LLM prompt for this step

> Implement Step 1 of issue #8 per `pr_info/steps/summary.md` and `pr_info/steps/step_1.md`. Add `get_isolated_connection()` as an abstract context-manager primitive on `DatabaseBackend`, with a no-op SQLite impl (yields the persistent connection) and a fresh-connection MSSQL impl (builds via `_build_connection_string`, closes on exit). Add tests per the step file. Run format / pytest / pylint / mypy and commit as one commit.
