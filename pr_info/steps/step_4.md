# Step 4 — `MSSQLBackend` implementation + unit tests

## Goal

Implement `MSSQLBackend.connect / close / execute_query / execute_update /
explain` against pyodbc, mirroring the `SQLiteBackend` **contract** (lazy +
idempotent + post-close `RuntimeError`). All unit tests monkeypatch
`pyodbc.connect` — no live DB. Integration tests live in Step 5.

## WHERE

| Action | Path |
|---|---|
| Modify | `src/mcp_tools_sql/backends/mssql.py` (replace `NotImplementedError` stubs) |
| Modify | `tests/backends/test_mssql.py` (add `TestLifecycle`, `TestQueries`, `TestConcurrency`, `TestErrorSanitization` classes) |

## WHAT

```python
class MSSQLBackend(DatabaseBackend):
    def __init__(self, config: ConnectionConfig) -> None: ...
    def connect(self) -> None: ...                # lazy, idempotent, thread-safe
    def close(self) -> None: ...                  # idempotent
    def execute_query(self, sql, params=None) -> list[dict[str, Any]]: ...
    def execute_update(self, sql, params=None) -> int: ...
    def explain(self, sql, params=None) -> str: ...
```

Private helpers:

```python
def _ensure_connected(self) -> Any: ...           # lazy-connect, returns conn
def _params_for_pyodbc(self, sql, params) -> tuple[str, list[Any]]: ...
```

## HOW — key implementation contracts

1. **State**: `self._connection`, `self._closed=False`,
   `self._connect_lock = threading.Lock()`.
2. **`connect()`**: SQLiteBackend pattern — lock-only-on-creation.
   - If `_connection is not None and not _closed`: return.
   - Acquire `_connect_lock`. Re-check inside lock. If `_closed`: raise
     `RuntimeError("Backend has been closed.")`. Build connection string
     via `_build_connection_string(self._config)`. Call
     `pyodbc.connect(conn_str, autocommit=True)`. On `pyodbc.Error`, sanitize
     by replacing the password value in the error message with `***` and
     re-raise the **same exception class** with the sanitized message.
3. **`close()`**: idempotent; if `_connection is not None`, call
   `.close()`; set `_connection = None`, `_closed = True`.
4. **Data methods** all do:
   - `conn = self._ensure_connected()` (calls `self.connect()`).
   - Translate `:name → ?` via
     `translate_named_to_qmark(sql)` → `(sql_q, ordered_names)`.
   - Build positional args list `[params[name] for name in ordered_names]`
     (use `{}` if params is None and the list is empty).
   - Open a fresh `cursor = conn.cursor()`; execute; collect; **close in
     `finally`**.
5. **`execute_query`** — `cursor.execute(sql_q, args)`, then
   `[dict(zip([d[0] for d in cursor.description], row)) for row in
   cursor.fetchall()]`.
6. **`execute_update`** — `cursor.execute(sql_q, args)`, return
   `cursor.rowcount`. No manual `commit()` (autocommit).
7. **`explain`** — under the cursor:
   ```
   cursor.execute("SET SHOWPLAN_TEXT ON")
   try:
       cursor.execute(sql_q, args)
       rows = cursor.fetchall()
   finally:
       cursor.execute("SET SHOWPLAN_TEXT OFF")
   return "\n".join(r[0] for r in rows if r and r[0])
   ```

## ALGORITHM — `connect()`

```
if self._connection is not None and not self._closed: return
with self._connect_lock:
    if self._closed: raise RuntimeError("Backend has been closed.")
    if self._connection is not None: return
    cs = _build_connection_string(self._config)
    try:
        self._connection = pyodbc.connect(cs, autocommit=True)
    except pyodbc.Error as exc:
        raise type(exc)(_sanitize(str(exc), self._config.password)) from exc
```

`_sanitize(msg, pw)` returns `msg.replace(pw, "***")` only when `pw` is
non-empty.

**Note on traceback preservation:** the re-raise uses `from exc` (not
`from None`) so the original pyodbc traceback is preserved in the chain.
The sanitized message still hides the password, but operators retain full
context (driver-level frames, ODBC SQLSTATE) for debugging.

### Contract for `params is None`

`execute_query` / `execute_update` / `explain` all accept `params=None`.
The implementation substitutes `params = {}` internally before building
the positional args list `[params[name] for name in ordered_names]`.

- **No placeholders + `params=None`** → works (empty `ordered_names`,
  empty args list, no `dict.__getitem__` ever invoked).
- **Placeholders present + `params=None`** → raises `KeyError(name)` —
  the natural result of looking up the first ordered name in the empty
  dict. This is the documented contract: callers must pass a dict when
  the SQL contains `:name` placeholders. No special pre-validation is
  needed; the `KeyError` is clear enough.

## DATA

- `execute_query` → `list[dict[str, Any]]` (column-name keyed dicts).
- `execute_update` → `int` (affected rows).
- `explain` → `str` (joined SHOWPLAN_TEXT output).

## Tests (write FIRST) — all monkeypatch `pyodbc.connect`

```python
# tests/backends/test_mssql.py (additions)

@pytest.fixture
def fake_pyodbc(monkeypatch):
    """Replace pyodbc with a fake module exposing connect() returning a Mock."""
    fake = types.ModuleType("pyodbc")
    fake.Error = type("Error", (Exception,), {})
    fake.connect = MagicMock(return_value=MagicMock(name="connection"))
    monkeypatch.setitem(sys.modules, "pyodbc", fake)
    return fake


def _cfg(**kw):
    base = dict(backend="mssql", host="h", port=1433, database="d",
                username="u", password="p")
    return ConnectionConfig(**{**base, **kw})


class TestLifecycle:
    def test_connect_lazy_no_call_at_init(fake_pyodbc):
        MSSQLBackend(_cfg())
        fake_pyodbc.connect.assert_not_called()

    def test_connect_idempotent(fake_pyodbc):
        b = MSSQLBackend(_cfg()); b.connect(); b.connect()
        assert fake_pyodbc.connect.call_count == 1

    def test_close_idempotent(fake_pyodbc):
        b = MSSQLBackend(_cfg()); b.connect(); b.close(); b.close()

    def test_post_close_raises_runtimeerror(fake_pyodbc):
        b = MSSQLBackend(_cfg()); b.connect(); b.close()
        with pytest.raises(RuntimeError, match="closed"):
            b.execute_query("SELECT 1")

    def test_context_manager_closes(fake_pyodbc):
        with MSSQLBackend(_cfg()) as b: b.execute_query("SELECT 1")
        # second exec raises
        with pytest.raises(RuntimeError):
            b.execute_query("SELECT 1")

    def test_lazy_connect_on_first_call(fake_pyodbc):
        b = MSSQLBackend(_cfg()); b.execute_query("SELECT 1")
        fake_pyodbc.connect.assert_called_once()


class TestQueries:
    def test_execute_query_translates_named_params(fake_pyodbc):
        conn = fake_pyodbc.connect.return_value
        cur = conn.cursor.return_value
        cur.description = [("col",)]
        cur.fetchall.return_value = [("v",)]
        b = MSSQLBackend(_cfg())
        rows = b.execute_query("SELECT col FROM t WHERE x = :x", {"x": 1})
        cur.execute.assert_called_once_with(
            "SELECT col FROM t WHERE x = ?", [1])
        assert rows == [{"col": "v"}]

    def test_execute_update_returns_rowcount(fake_pyodbc):
        cur = fake_pyodbc.connect.return_value.cursor.return_value
        cur.rowcount = 3
        b = MSSQLBackend(_cfg())
        assert b.execute_update("UPDATE t SET x=:x", {"x": 1}) == 3

    def test_execute_query_no_params_no_placeholders(fake_pyodbc):
        # params=None + SQL has no placeholders → must succeed.
        # Guards against a regression where the impl does dict.__getitem__
        # on None.
        conn = fake_pyodbc.connect.return_value
        cur = conn.cursor.return_value
        cur.description = [("one",)]
        cur.fetchall.return_value = [(1,)]
        b = MSSQLBackend(_cfg())
        rows = b.execute_query("SELECT 1")
        assert rows == [{"one": 1}]

    def test_execute_query_placeholders_but_none_params_raises(fake_pyodbc):
        # Documented contract: SQL has :x but params=None → KeyError("x").
        # This is the natural result of looking up the ordered name in the
        # empty dict substituted for None. See ALGORITHM section.
        b = MSSQLBackend(_cfg())
        with pytest.raises(KeyError, match="x"):
            b.execute_query("SELECT :x", None)

    def test_autocommit_passed_to_pyodbc(fake_pyodbc):
        MSSQLBackend(_cfg()).connect()
        kwargs = fake_pyodbc.connect.call_args.kwargs
        assert kwargs.get("autocommit") is True

    def test_cursor_closed_after_call(fake_pyodbc):
        cur = fake_pyodbc.connect.return_value.cursor.return_value
        b = MSSQLBackend(_cfg()); b.execute_query("SELECT 1")
        cur.close.assert_called()

    def test_explain_wraps_with_showplan(fake_pyodbc):
        cur = fake_pyodbc.connect.return_value.cursor.return_value
        cur.fetchall.return_value = [("plan-line",)]
        b = MSSQLBackend(_cfg()); plan = b.explain("SELECT :a", {"a": 1})
        executed = [c.args[0] for c in cur.execute.call_args_list]
        assert executed[0] == "SET SHOWPLAN_TEXT ON"
        assert "?" in executed[1]                         # translated
        assert executed[-1] == "SET SHOWPLAN_TEXT OFF"
        assert plan == "plan-line"

    def test_explain_resets_showplan_on_error(fake_pyodbc):
        cur = fake_pyodbc.connect.return_value.cursor.return_value
        cur.execute.side_effect = [None, RuntimeError("boom"), None]
        b = MSSQLBackend(_cfg())
        with pytest.raises(RuntimeError):
            b.explain("SELECT 1")
        executed = [c.args[0] for c in cur.execute.call_args_list]
        assert executed[-1] == "SET SHOWPLAN_TEXT OFF"


class TestConcurrency:
    def test_concurrent_connect_calls_pyodbc_once(fake_pyodbc):
        b = MSSQLBackend(_cfg())
        barrier = threading.Barrier(5)
        def worker(): barrier.wait(); b.connect()
        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert fake_pyodbc.connect.call_count == 1


class TestErrorSanitization:
    def test_password_redacted_in_pyodbc_error(fake_pyodbc):
        fake_pyodbc.connect.side_effect = fake_pyodbc.Error(
            "login failed for PWD=supersecret")
        b = MSSQLBackend(_cfg(password="supersecret"))
        with pytest.raises(fake_pyodbc.Error) as exc:
            b.connect()
        assert "supersecret" not in str(exc.value)
        assert "***" in str(exc.value)
```

## Checks

- `mcp__tools-py__run_pylint_check`
- `mcp__tools-py__run_mypy_check`
- `mcp__tools-py__run_pytest_check(extra_args=["-n", "auto", "-m", "not git_integration and not claude_cli_integration and not claude_api_integration and not formatter_integration and not github_integration and not langchain_integration"])`
- `./tools/format_all.sh`
- Single commit.

## LLM Prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_4.md`. Implement
> the `MSSQLBackend` lifecycle and data methods exactly as specified —
> lazy `connect()` with `threading.Lock`, idempotent `close()`, post-close
> `RuntimeError`, per-call cursor (closed in `finally`), `autocommit=True`,
> `:name → ?` translation via `utils.sql_placeholders`, password
> sanitization on `pyodbc.Error`, and `SET SHOWPLAN_TEXT ON/OFF` wrapped in
> `try/finally`. Tests in `tests/backends/test_mssql.py` first (TDD,
> monkeypatched pyodbc). Run pylint, mypy, pytest via MCP tools per
> CLAUDE.md after every edit. End with a single commit.
