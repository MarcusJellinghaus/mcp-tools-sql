# Step 4 – Tool-level timeout branches (count, validate, summarize, update)

## LLM prompt
Read `pr_info/steps/summary.md` (sections 2 and 7) and this file. Implement
step 4 only, test-first: `count_records`, `validate_sql` and `summarize_columns`
return the timeout message plus `Use a narrower query.` instead of
`Invalid SQL …`; update tools return the bare timeout message; `_explain`
translates driver timeouts from its raw SHOWPLAN cursor. Run pylint, pytest
(`-n auto`), mypy, lint-imports; format; one commit.

## WHERE
- `src/mcp_tools_sql/formatting.py` – hint constants
- `src/mcp_tools_sql/count_tools.py`
- `src/mcp_tools_sql/validation_tools.py`
- `src/mcp_tools_sql/summarize/tools.py`
- `src/mcp_tools_sql/update_tools.py`
- `tach.toml` – add `{ path = "mcp_tools_sql.formatting" }` to `count_tools`
  `depends_on`
- Tests: `tests/test_tool_timeouts.py` (new)

## WHAT
```python
# formatting.py
TIMEOUT_HINT_PARAMS = "Use more selective parameters."
TIMEOUT_HINT_NARROWER = "Use a narrower query."

# validation_tools.py
def _explain(backend, backend_name, sql, params, timeout_seconds: int) -> str: ...
```

## HOW
- `count_tools.core` / `validation_tools.core` / `summarize core`: add
  `except QueryTimeoutError as exc: return f"{exc} {TIMEOUT_HINT_NARROWER}"`
  as the **first** handler (before `_INVALID_SQL_EXC` / `INVALID_SQL_EXC` and
  before the generic `except Exception`).
- `_explain` SQL Server path: keep `with backend.get_isolated_connection() as conn:`
  outside; wrap only the cursor work in `try/except Exception` that calls
  `translate_timeout(exc, timeout_seconds)` and raises the result `from exc`
  when not `None`, else re-raises. The caller passes
  `target.config.query_timeout_seconds`. The SQLite path already raises
  `QueryTimeoutError` from `backend.explain`.
- `update_tools.body`: wrap `backend.execute_update(...)` in
  `try/except QueryTimeoutError as exc: return str(exc)` (no hint).
- `verify` needs no change: it builds backends from the same `ConnectionConfig`,
  so the timeout applies, and `_check_sql_explain` already reports `str(exc)`.

## ALGORITHM
```
try: result = backend call
except QueryTimeoutError as exc: return f"{exc} Use a narrower query."   # update tools: return str(exc)
except <existing driver errors>: return "Invalid SQL. ..."
```

## DATA
Tool return strings:
- count/validate/summarize: `Query aborted after N s (statement timeout). Use a narrower query.`
- update tools: `Query aborted after N s (statement timeout).`

## Tests (write first)
`tests/test_tool_timeouts.py`, using a small fake `DatabaseBackend` whose
`execute_readonly_query` / `explain` / `execute_update` raise
`QueryTimeoutError(30)` (registry/targets via `tests.target_helpers.single_target`):
- `count_records`, `validate_sql`, `summarize_columns` (table source) each return
  exactly `Query aborted after 30 s (statement timeout). Use a narrower query.`
  and do not contain `Invalid SQL`.
- An update tool returns exactly `Query aborted after 30 s (statement timeout).`
- `validate_sql` on a T-SQL target whose isolated connection's
  `cursor.execute` raises an exception with `args = ("HYT00", "...")` returns
  the timeout message with `Use a narrower query.`
- Same with `args = ("42000", ...)` still returns `Invalid SQL …` or the
  existing verdict (regression guard).
