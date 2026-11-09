# Step 6 — SQLite backend translates driver errors

See `pr_info/steps/summary.md` for the overall design.

## Kind
Restructure (behaviour-preserving for users: messages and exit codes identical thanks to
step 5). TDD: tests first.

## WHERE
- `src/mcp_tools_sql/backends/sqlite.py`
- Tests: `tests/backends/test_sqlite.py`, `tests/backends/test_sqlite_timeout.py`,
  `tests/backends/test_batched_read.py`, plus any non-owner test that asserts a raw
  `sqlite3.*` exception escaping a backend call (find with `search_files` for
  `pytest.raises(sqlite3`).

## WHAT
```python
_CONNECTION_ERRORS: tuple[type[sqlite3.Error], ...] = (sqlite3.OperationalError, sqlite3.InterfaceError)

@contextmanager
def _driver_errors() -> Iterator[None]:
    """Translate sqlite3.Error into BackendError / BackendConnectionError."""
```

## HOW
Wrap the **whole body** of each public driver-touching method in `with _driver_errors():`
— `connect`, `close`, `execute_query`, `execute_readonly_query`,
`iter_readonly_batches` (inside the generator body, around the existing try/finally),
`execute_readonly_query_with_columns`, `execute_update`, `explain`. This also covers
`sqlite3.connect` and `PRAGMA query_only`, which run outside `_statement_deadline`.
`_statement_deadline` stays as is and stays **inside** `_driver_errors`, so a statement
timeout becomes `QueryTimeoutError` first (it reads the raw `sqlite_errorcode`).
`get_isolated_connection` is left untouched (removed in step 8).
Update the `_statement_deadline` docstring "Raises" line only if needed; add
`BackendError` to the `Raises:` sections of the wrapped methods.

## ALGORITHM
```
@contextmanager
def _driver_errors():
    try:
        yield
    except sqlite3.Error as exc:          # driver errors only
        raise wrap_driver_error(exc, _CONNECTION_ERRORS) from exc
```
`ValueError` (empty path), `RuntimeError` (closed), `QueryTimeoutError`, `KeyError` pass unchanged.

## DATA
Unchanged return values; exceptions now `BackendError` / `BackendConnectionError` with
`original_class` equal to the sqlite3 class name and identical `str()`.

## Tests first (owner tests)
- `execute_query("SELECT * FROM missing")` → `BackendConnectionError`, `original_class == "OperationalError"`,
  `str` contains `"no such table"`, `__cause__` is `sqlite3.OperationalError`.
- `execute_readonly_query("INSERT ...")` (query_only) → `BackendConnectionError` (`OperationalError`).
- `explain("SELECT :x", None)` (missing binding) → plain `BackendError` (`ProgrammingError`).
- `connect()` with a path inside a non-existent directory → `BackendConnectionError`.
- `iter_readonly_batches` on a missing table → `BackendConnectionError` on first `next()`.
- Statement timeout still raises `QueryTimeoutError` (existing timeout tests keep passing).
- Empty path still `ValueError`; closed backend still `RuntimeError`.
- Rewrite existing owner assertions `pytest.raises(sqlite3.X)` to the neutral class plus
  `original_class == "X"`.

## Verification
- `tests/cli/test_tool.py` exit 1 for "no such table" still passes (via `BackendConnectionError`).
- pylint, pytest (`-n auto`), mypy, lint-imports, ruff green; format; one commit.

## Commit
`refactor(backends): translate sqlite3 errors into neutral backend errors`

## LLM prompt
> Read `pr_info/steps/summary.md` and `pr_info/steps/step_6.md`. Write/adjust the SQLite owner
> tests first, then add `_driver_errors()` to `src/mcp_tools_sql/backends/sqlite.py` and wrap
> every public driver-touching method body with it, keeping `_statement_deadline` inside so
> timeouts translate first. Translate only `sqlite3.Error`. Fix any test that expected raw
> sqlite3 exceptions from a backend call. Use MCP tools only. Run pylint, pytest (`-n auto`),
> mypy, lint-imports and ruff; all must pass. Format, then one commit.
