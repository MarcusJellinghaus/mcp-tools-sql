# Issue #10 — Server setup and CLI entry point

Closes M1 by wiring `init` / `verify` / built-in tools into a working MCP server,
plus a shared per-tool-call logging helper that #5 / #6 / #8 will reuse.

Out of scope (other M1 issues): SELECT registration body (#5), UPDATE registration
body (#6), `validate_sql` (#8), MSSQL backend (#7).

---

## Architectural / design changes

### 1. Backend contract — `execute_query` (and friends) imply connected

`DatabaseBackend.execute_query` / `execute_update` / `explain` now lazy-connect on
first call. The contract change is documented in `backends/base.py`. `SQLiteBackend`
implements it with a `threading.Lock` (matches its sync, `check_same_thread=False`
concurrency model).

A `_closed` flag is added so post-`close()` calls raise rather than silently
reconnecting (matches the M1 "no auto-reconnect" rule). `connect()` uses a fast
path that returns immediately when `_connection` is already set and the backend
isn't closed; only first-call setup acquires `_connect_lock`. The `_closed` check
sits inside the locked region to avoid races against `close()`. No parallel
`_connected` bool — the existing `_connection is not None` check is the source of
truth.

`verify_connection` is untouched: it keeps its eager connect + `SELECT 1` probe.
The lazy contract applies only to the server-command path.

### 2. New module `mcp_tools_sql.tool_logging`

A small async-context-manager helper:

```python
async with log_tool_call(name, params) as rec:
    rows = backend.execute_query(...)
    rec.record(len(rows), len(rows[0]) if rows else 0)
    return format_rows(rows, max_rows)
```

Sits at the **infrastructure** layer (peer of `formatting`). Body uses only
stdlib, so its `tach.toml` `depends_on = []`. Built-in tools, plus #5 / #6 / #8
later, all import the same helper.

Logging shape:
- INFO on success: `tool=<name> rows=<n> cols=<m> duration_ms=<k>`
- DEBUG: param keys + values (and resolved SQL when callers pass it)
- ERROR: `tool=<name> duration_ms=<k> error=<exc>`

### 3. Server wiring — `run_server(args)` in `server.py`

A single function does the linear wiring:

```
discover_query_config → load_query_config → load_database_config
→ resolve_connection → create_backend → ToolServer → run, in try/finally
```

`main.py` calls `run_server(args)` and translates exceptions to exit codes:

| Outcome | Exit | UX |
|---|---|---|
| Clean exit | 0 | — |
| `KeyboardInterrupt` (Ctrl+C) | 130 | POSIX SIGINT convention; backend.close() still runs |
| Pre-`mcp.run()` `ValueError` / `OSError` (config / unknown backend / permission) | 2 | Friendly stderr + hint pointing at `verify`; traceback only at `--log-level=DEBUG` |
| Runtime errors (post-`mcp.run()`) | — | Flow through `tool_logging` ERROR path on first tool call |

`main([])` (no subcommand) → server. Existing `--help` / `-h` / `help` still print
help and exit 0.

`_register_configured_tools` stays a no-op stub (#5 / #6).

### 4. Architecture-enforcement updates

- `.importlinter`: `mcp_tools_sql.tool_logging` added to the infrastructure layer
  alongside `formatting`.
- `tach.toml`: new module entry for `tool_logging` (`depends_on = []` — stdlib
  only); the four tool-implementation modules (`schema_tools`, `query_tools`,
  `update_tools`, `validation_tools`) gain `tool_logging` in their `depends_on`
  so #5 / #6 / #8 can import it without further config churn.
- `docs/architecture/architecture.md`: one row added to the modules table.

---

## Files created

```
pr_info/steps/summary.md
pr_info/steps/step_1.md
pr_info/steps/step_2.md
pr_info/steps/step_3.md
pr_info/steps/step_4.md

src/mcp_tools_sql/tool_logging.py
tests/test_tool_logging.py
tests/test_server.py
```

## Files modified

```
src/mcp_tools_sql/backends/base.py            # contract docstring
src/mcp_tools_sql/backends/sqlite.py          # lazy-connect + lock + _closed
src/mcp_tools_sql/schema_tools.py             # wire log_tool_call into _build_tool_fn
src/mcp_tools_sql/server.py                   # add run_server()
src/mcp_tools_sql/main.py                     # server dispatch + friendly errors

tests/backends/test_sqlite.py                 # update post-connect/post-close tests
tests/test_schema_tools.py                    # add caplog assertion for builtin tool
tests/cli/test_main_dispatch.py               # replace help-on-no-args with server-dispatch

.importlinter                                 # add tool_logging to layers
tach.toml                                     # add tool_logging module + tool deps
docs/architecture/architecture.md             # one-row docs update
```

## Steps overview

| Step | Scope | Depends on |
|---|---|---|
| 1 | Backend lazy-connect (`backends/sqlite.py`, base contract docstring, sqlite tests) | — |
| 2 | New `tool_logging.py` + tests + architecture wiring | — |
| 3 | Wire `log_tool_call` into `schema_tools._build_tool_fn` | Step 2 |
| 4 | `run_server()` + `main` dispatch + server tests + dispatch test split | Step 1 |

Steps 1 and 2 are independent. Step 3 needs Step 2. Step 4 needs Step 1.

---

## Mandatory checks per step

After each step, all three must pass:

```
mcp__tools-py__run_pylint_check
mcp__tools-py__run_pytest_check  (extra_args: ["-n", "auto", "-m", "not git_integration and not claude_cli_integration and not claude_api_integration and not formatter_integration and not github_integration and not langchain_integration"])
mcp__tools-py__run_mypy_check
```

Plus `lint-imports` and `tach check` for steps that touch architecture config.
