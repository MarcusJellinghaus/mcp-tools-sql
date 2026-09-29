# Step 3 — one connect path for both `pyodbc.connect` sites

See [summary.md](./summary.md) for context. Depends on steps 1 and 2.

Scope: the two connect sites. This step closes the second half of the issue —
`get_isolated_connection` reaching `validate_sql`'s error text unprotected — and
routes the connect-attempt debug log through the structural builder from step 2.

## WHERE

`src/mcp_tools_sql/backends/mssql.py`, class `MSSQLBackend`:

- new private method `_open_connection` (place it next to `connect`)
- `connect` (line 106) — body of the `try/except` replaced by a call
- `get_isolated_connection` (line 256) — bare `pyodbc.connect` replaced by a call

`tests/backends/test_mssql.py`:

- `TestIsolatedConnection` (line 465) — new redaction test, `fake_pyodbc` fixture
  is already available there
- `TestConnectDebugLogging` (line 533) — extend the attempt-log test

## WHAT

```python
def _open_connection(self) -> Any:
    """Open a fresh pyodbc connection with the password redacted from errors."""
```

A method, not a module-level function: both callers are methods on this class and
the only input is `self._config`.

## HOW

- Keep `import pyodbc` **inside** the method. pyodbc is an optional dependency and
  the tests monkeypatch `sys.modules["pyodbc"]`, so a module-level import would
  break both.
- Keep `autocommit=True` explicit.
- `connect()` keeps its lock, closed-check, and idempotency guard; only the
  build/log/connect/except block moves out.
- `get_isolated_connection()` keeps its `@contextmanager`, `yield`, and
  `finally: conn.close()`.

## ALGORITHM

```
_open_connection(self):
    import pyodbc
    conn_str = _build_connection_string(self._config)
    logger.debug("MSSQL connect attempt: %s",
                 build_sanitized_connection_string(self._config))   # structural, step 2
    try:
        return pyodbc.connect(conn_str, autocommit=True)
    except pyodbc.Error as exc:
        exc.args = tuple(_sanitize(a, self._config.password) if isinstance(a, str) else a
                         for a in exc.args)
        logger.debug("MSSQL connect failed: %s %r", type(exc).__name__, exc.args)
        raise
```

`connect()` becomes `self._connection = self._open_connection()` inside the
existing lock; `get_isolated_connection()` becomes
`conn = self._open_connection()` before its `try/yield/finally`.

## DATA

Returns the live pyodbc connection object (`Any`, matching `self._connection` and
the `Iterator[Any]` the context manager yields). On failure re-raises the original
`pyodbc.Error` instance — type, sqlstate, and traceback preserved, `args`
redacted in place.

## Behaviour change (intended)

`get_isolated_connection` starts emitting a connect-attempt debug line it does not
emit today — once per `validate_sql` call on MSSQL. Intended, not a regression.

## TDD

1. In `TestIsolatedConnection`, add a redaction test: set
   `fake_pyodbc.connect.side_effect = fake_pyodbc.OperationalError("08001", f"Login failed; PWD={_odbc_escape(pw)}")`,
   build `MSSQLBackend(_cfg(password=pw))`, enter `get_isolated_connection()` in a
   `pytest.raises(fake_pyodbc.Error)`, and assert
   `assert_no_leak(str(exc.value), pw)` and `"***" in str(exc.value)`.
   Parametrize over `LEAKY_PASSWORDS`. This fails today — the bare
   `pyodbc.connect` has no handler.
2. Extend `test_connect_logs_redacted_conn_string` (lines 536-552) to parametrize
   over `LEAKY_PASSWORDS` and assert `assert_no_leak(line, pw)` alongside the
   existing `"PWD=***" in line`. This is **green before this step**: step 1 made
   `_sanitize` strip the escaped form, and the attempt log at `mssql.py:131-134`
   already runs through `_sanitize`. Keep it as a regression guard for routing
   the log through `build_sanitized_connection_string` — do not expect it to
   fail, and do not weaken it to manufacture a failure.
3. Confirm item 1 is red — it is the only red test in this step; the bare
   `pyodbc.connect` in `get_isolated_connection` has no handler. Then extract
   `_open_connection` and wire up both call sites.
4. Update docstrings: `connect`'s `Raises:` block, and
   `get_isolated_connection`'s — it gains the redaction guarantee and the debug
   line.
5. Re-run. `test_connect_idempotent`, `test_concurrent_connect_calls_pyodbc_once`,
   `test_autocommit_passed_for_isolated_connection`,
   `TestErrorSanitization::test_password_redacted_in_pyodbc_error`, and
   `test_connect_failure_logs_exception_details` must all pass unmodified.

## Checks

`mcp__mcp-tools-py__run_format_code`, then pylint, pytest (`-n auto`), mypy, plus
vulture and lint-imports (a new private method can trip vulture; no imports move,
so lint-imports is a formality). Commit: tests + implementation together.

Finally, delete `.scratch/` if any probe was written, and tick the step off in
`pr_info/TASK_TRACKER.md`.

## LLM prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_3.md`. Steps 1 and 2 are
> already committed.
>
> Implement step 3 only: add a private `MSSQLBackend._open_connection()` to
> `src/mcp_tools_sql/backends/mssql.py` that owns the connect-attempt debug log
> (routed through `build_sanitized_connection_string`) and the args-redacting
> `try/except`, and call it from both `connect()` and
> `get_isolated_connection()`. Keep `import pyodbc` inside the method — the tests
> monkeypatch `sys.modules["pyodbc"]`. Keep `autocommit=True` explicit.
>
> In `tests/backends/test_mssql.py`, add a parametrized redaction test for a
> failing `get_isolated_connection` to `TestIsolatedConnection`, and parametrize
> `test_connect_logs_redacted_conn_string` over `LEAKY_PASSWORDS` with
> `assert_no_leak`. Only the isolated-connection test is red before you
> implement — confirm that one fails. The attempt-log test is already green
> because step 1 fixed `_sanitize`; it is a regression guard for routing the log
> through `build_sanitized_connection_string`, so keep it green, do not weaken
> it to force a failure.
>
> Do not touch `src/mcp_tools_sql/validation_tools.py` — the fix belongs in the
> backend, which owns the credential.
>
> Run `run_format_code`, then pylint, pytest with `extra_args: ["-n", "auto"]`,
> mypy, vulture, and lint-imports. All must pass. Then make exactly one commit.
