# Step 3 – SQL Server login + statement timeouts

## LLM prompt
Read `pr_info/steps/summary.md` (sections 1 and 2) and this file. Implement
step 3 only, test-first: set the login timeout and statement timeout in
`MSSQLBackend._open_connection`, and translate `HYT00` to `QueryTimeoutError`
for errors raised by execute/fetch only. Run pylint, pytest (`-n auto`), mypy;
format; one commit.

## WHERE
- `src/mcp_tools_sql/backends/mssql.py`
- Tests: `tests/backends/test_mssql_timeout.py` (new, uses the existing
  `fake_pyodbc` fixture from `tests/backends/conftest.py`)

## WHAT
```python
class MSSQLBackend(DatabaseBackend):
    def _open_connection(self) -> Any: ...  # connect(timeout=...) + conn.timeout

    @contextmanager
    def _timeouts(self) -> Iterator[None]:
        """Translate HYT00 from execute/fetch into QueryTimeoutError."""
```

## HOW
- `_open_connection`:
  `conn = pyodbc.connect(conn_str, autocommit=True, timeout=self._config.connect_timeout_seconds)`
  inside the existing `try` (password redaction unchanged; a login `HYT00` keeps
  propagating as the original `pyodbc.Error`). After the `try`, set
  `conn.timeout = self._config.query_timeout_seconds` and return `conn`.
- Wrap only the cursor work in `with self._timeouts():` in `execute_query`,
  `execute_readonly_query_with_columns`, `execute_update`, `explain`. Call
  `_ensure_connected()` **before** entering the block so a connect error is never
  translated.
- Update the `_open_connection` / class docstrings: both timeouts, and that
  `HYT00` from `connect()` is a login timeout and is not translated.

## ALGORITHM
```
_timeouts():
    try: yield
    except Exception as exc:
        t = translate_timeout(exc, self._config.query_timeout_seconds)
        if t is None: raise
        raise t from exc
```

## DATA
No new data structures. Raised: `QueryTimeoutError` (statement) or the original
pyodbc error.

## Tests (write first)
`tests/backends/test_mssql_timeout.py`:
- `connect()` → `fake_pyodbc.connect` called with `timeout=15` (default) and
  with the configured value (`_cfg(connect_timeout_seconds=7)`); the returned
  connection has `.timeout == 30` / configured value.
- `get_isolated_connection()` → same two settings on the fresh connection.
- `cursor.execute` raising `fake_pyodbc.OperationalError("HYT00", "timeout")`
  → `execute_query`, `execute_update`, `explain` raise `QueryTimeoutError`.
- `cursor.fetchall` raising the same → `QueryTimeoutError`.
- `cursor.execute` raising `OperationalError("42000", ...)` → original error.
- `fake_pyodbc.connect` raising `OperationalError("HYT00", ...)` → the pyodbc
  error propagates unchanged (not `QueryTimeoutError`).
