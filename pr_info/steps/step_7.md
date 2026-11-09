# Step 7 — MSSQL backend translates driver errors

See `pr_info/steps/summary.md` for the overall design.

## Kind
Restructure. TDD: tests first.

## WHERE
- `src/mcp_tools_sql/backends/mssql.py`
- `tests/backends/conftest.py` — `fake_pyodbc` gains `InterfaceError`.
- New `tests/backends/test_mssql_errors.py`; adjust `tests/backends/test_mssql.py`,
  `tests/backends/test_mssql_timeout.py` where they pin raw `fake_pyodbc` exception classes.

## WHAT
```python
def _translate_pyodbc(exc: BaseException) -> BackendError | None:
    """Neutral exception for a pyodbc error, or None if exc is not one.

    Resolves pyodbc via sys.modules at call time (never imports it), so the
    module stays importable without the driver and works with fake_pyodbc.
    """
```

## HOW
- No module-scope `import pyodbc`. `_translate_pyodbc` reads `sys.modules.get("pyodbc")`;
  `Error` = `getattr(mod, "Error", None)`; connection types =
  `getattr(mod, "OperationalError", None)`, `getattr(mod, "InterfaceError", None)` (drop `None`s).
- `_open_connection`: after the existing in-place redaction and debug log, replace the bare
  `raise` with `raise _translate_pyodbc(exc) or exc from exc`-equivalent (see ALGORITHM).
  A login `HYT00` therefore becomes `BackendConnectionError` — **never** `QueryTimeoutError`.
- `_timeouts()`: order = (1) `BackendError` passes through untouched (protects a translated login
  `HYT00` from `translate_timeout`), (2) statement timeout → `QueryTimeoutError`,
  (3) pyodbc error → neutral, (4) anything else (`KeyError`, `TypeError`, `SqlParseError`,
  `RuntimeError`) re-raised unchanged.
- Each execute method: move `cursor = conn.cursor()` and the `finally: cursor.close()` inside
  `with self._timeouts():` so cursor creation/close are translated too. `_ensure_connected()` and
  `_params_for_pyodbc()` stay **outside** (connect errors are already neutral; `KeyError`/
  `SqlParseError` must stay untouched). `iter_readonly_batches`: wrap its whole try/except/finally
  in `with self._timeouts():` (GeneratorExit is not an `Exception`, so cancel logic is unaffected).
- `close()`: wrap `self._connection.close()` in `with self._timeouts():`.
- `explain` (persistent path) gets the same cursor-inside-`_timeouts` shape; SHOWPLAN move is step 8.
- `fake_pyodbc`: add `fake.InterfaceError = type("InterfaceError", (error_cls,), {})`.

## ALGORITHM
```
_timeouts():
    try: yield
    except Exception as exc:
        if isinstance(exc, BackendError): raise
        if translate_timeout(exc, seconds) is not None: raise QueryTimeoutError(seconds) from exc
        neutral = _translate_pyodbc(exc)
        if neutral is None: raise
        raise neutral from exc

_open_connection():  ... except pyodbc.Error as exc: <redact args>; <log>; raise _translate_pyodbc(exc) from exc
```
(`_translate_pyodbc` cannot return `None` there because `exc` is a `pyodbc.Error`; assert or
fall back to `raise` to satisfy mypy.)

## DATA
`BackendError.args` == redacted driver args; `original_class` == pyodbc class name.

## Tests first (`tests/backends/test_mssql_errors.py`, uses `fake_pyodbc`)
- cursor `execute` raising `fake.Error("42000", "bad")` → `BackendError` (not connection),
  `original_class == "Error"`, `str` equals `str(fake.Error("42000", "bad"))`.
- `fake.OperationalError` / `fake.InterfaceError` → `BackendConnectionError`.
- `execute` raising `fake.OperationalError("HYT00", "timeout")` → `QueryTimeoutError`.
- `fake.connect` raising `fake.OperationalError("HYT00", "login timeout")` → `BackendConnectionError`,
  not `QueryTimeoutError`.
- `fake.connect` raising an error echoing the password → `BackendConnectionError` whose `str`
  passes `assert_no_leak` for every `LEAKY_PASSWORDS` entry.
- `conn.cursor()` raising `fake.Error` → `BackendError`.
- Missing param → `KeyError` unchanged; `SqlParseError` from `translate_named_to_qmark` unchanged.
- `importlib.reload`-free check: `import mcp_tools_sql.backends.mssql` works with
  `sys.modules["pyodbc"]` set to `None` (monkeypatch).
- Rewrite existing owner assertions pinning raw `fake.Error`/`fake.OperationalError` to the
  neutral classes (keep their redaction / sqlstate checks on `.args`).

## Verification
pylint, pytest (`-n auto`), mypy, lint-imports, ruff green; format; one commit.

## Commit
`refactor(backends): translate pyodbc errors into neutral backend errors`

## LLM prompt
> Read `pr_info/steps/summary.md` and `pr_info/steps/step_7.md`. Add `InterfaceError` to the
> `fake_pyodbc` fixture and write `tests/backends/test_mssql_errors.py` first. Then add
> `_translate_pyodbc` to `src/mcp_tools_sql/backends/mssql.py`, translate in `_open_connection`
> after redaction, extend `_timeouts()` in the order given, and move cursor creation/close inside
> `_timeouts()`. Never import pyodbc at module scope; translate only pyodbc errors; a login
> HYT00 must not become `QueryTimeoutError`. Use MCP tools only. Run pylint, pytest
> (`-n auto`), mypy, lint-imports and ruff; all must pass. Format, then one commit.
