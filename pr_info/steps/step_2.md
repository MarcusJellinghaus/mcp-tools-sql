# Step 2 — `tool_logging.py` async-context-manager helper

## LLM prompt

> Read `pr_info/steps/summary.md` and then implement Step 2 in
> `pr_info/steps/step_2.md`. TDD: write `tests/test_tool_logging.py` first, then
> the module, then update `.importlinter` and `tach.toml`. Run pylint + pytest +
> mypy + lint-imports + tach check. One commit at the end.

## Goal

Self-contained `tool_logging` module exposing a single async context manager
`log_tool_call(name, params, *, sql=None)`. Built-in tools (Step 3) and #5 / #6 /
#8 will all import from here.

---

## WHERE

- `src/mcp_tools_sql/tool_logging.py` — new module.
- `tests/test_tool_logging.py` — new tests.
- `.importlinter` — add to infrastructure layer alongside `formatting`.
- `tach.toml` — new `[[modules]]` entry depending only on `utils`.
- `docs/architecture/architecture.md` — append one row to the modules table.

## WHAT

Module-level API:

```python
@dataclass
class ToolCallRecord:
    rows: int = 0
    cols: int = 0
    def record(self, rows: int, cols: int) -> None: ...

@asynccontextmanager
async def log_tool_call(
    name: str,
    params: Mapping[str, Any] | None = None,
    *,
    sql: str | None = None,
) -> AsyncIterator[ToolCallRecord]: ...
```

## HOW

- Use `contextlib.asynccontextmanager` — keeps the implementation under ~30 LOC.
- Use `time.monotonic()` for duration; report as `int(...*1000)` ms.
- Logger: `logging.getLogger(__name__)`.
- DEBUG entry log emits `tool=<name> param_keys=<sorted-keys> param_values=<values> sql=<sql>`.
  When `sql is None`, omit the `sql=` field.
- INFO success log: `tool=<name> rows=<n> cols=<m> duration_ms=<k>`.
- ERROR log: `tool=<name> duration_ms=<k> error=<exc>`. Re-raise the exception.

## ALGORITHM

```
log_tool_call(name, params, sql=None):
    rec = ToolCallRecord()
    start = time.monotonic()
    log.debug("tool=%s param_keys=%s param_values=%s [sql=%s]", name, ...)
    try:
        yield rec
    except Exception as exc:
        log.error("tool=%s duration_ms=%d error=%s", name, dur_ms, exc)
        raise
    else:
        log.info("tool=%s rows=%d cols=%d duration_ms=%d", name, rec.rows, rec.cols, dur_ms)
```

## DATA

Returns: an async iterator yielding a `ToolCallRecord` whose `rows`/`cols` start
at 0. Caller mutates via `record(rows, cols)`. No return value from the helper.

---

## Tests (TDD — write first)

In `tests/test_tool_logging.py`, all use `pytest`'s built-in `caplog` and
`@pytest.mark.asyncio` (the project already pulls in `pytest-asyncio`; if not,
use `asyncio.run(...)` directly inside a sync test).

1. **`test_info_on_success`**:
   ```python
   async with log_tool_call("read_tables", {"schema": "dbo"}) as rec:
       rec.record(rows=5, cols=3)
   # assert one INFO record with text "tool=read_tables rows=5 cols=3 duration_ms="
   ```

2. **`test_debug_includes_param_keys_and_values`**: at `caplog.set_level(DEBUG)`,
   assert the DEBUG record contains `param_keys=` and `param_values=` (and `sql=`
   when `sql=...` is passed).

3. **`test_error_path_logs_duration_and_reraises`**:
   ```python
   with pytest.raises(RuntimeError, match="boom"):
       async with log_tool_call("x", {}) as rec:
           raise RuntimeError("boom")
   # assert one ERROR record matching r"tool=x duration_ms=\d+ error=boom"
   ```

4. **`test_record_defaults_zero`**: not calling `rec.record(...)` produces an
   INFO line with `rows=0 cols=0`.

## Architecture wiring

- `.importlinter` layers — change the line:
  ```
  mcp_tools_sql.backends | mcp_tools_sql.formatting
  ```
  to:
  ```
  mcp_tools_sql.backends | mcp_tools_sql.formatting | mcp_tools_sql.tool_logging
  ```

- `tach.toml` — add:
  ```toml
  [[modules]]
  path = "mcp_tools_sql.tool_logging"
  layer = "infrastructure"
  depends_on = [
      { path = "mcp_tools_sql.utils" },
  ]
  ```

- `docs/architecture/architecture.md` — append row in the Key Modules table:
  ```
  | `tool_logging.py` | Per-tool-call logging context manager (INFO counts, DEBUG params, ERROR duration) |
  ```

## Acceptance

- All three checks green.
- `mcp__tools-py__run_lint_imports_check` — green.
- `mcp__tools-py__run_tach_check` — green.
- One commit: `feat(tool_logging): add async log_tool_call context manager`.
