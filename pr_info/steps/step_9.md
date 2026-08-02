# Step 9 — Extract shared `execute_and_format` core from `build_query_body`

See `pr_info/steps/summary.md` → "Architectural / design changes". This is a
**pure, behaviour-preserving refactor** that lands *before* the schema-tool
feature work (Step 10) so that step can delegate to a single execution+format
core instead of duplicating it. No feature behaviour changes here.

## WHERE
- `src/mcp_tools_sql/query_helpers.py`
- Tests: `tests/test_query_tools.py` (existing assertions, unchanged)

## WHAT
Extract the execution+format tail of `build_query_body` into a reusable helper:
```python
async def execute_and_format(name, resolved_sql, sql_params, backend, config,
                             filter_kwarg, truncation_hint, kwargs) -> str:
    """Shared body core: max_rows cap + note, filter pop, param strip,
    log_tool_call, execute_query, apply_filter, format_rows."""
```
`build_query_body` keeps its public signature and behaviour; its registration-time
closure captures `backend`/`resolved_sql`/`sql_params` and now calls
`execute_and_format` for the shared tail.

## HOW
Move the max_rows / filter / logging / execute / format logic verbatim out of
`build_query_body`'s inner function into `execute_and_format`, then have
`build_query_body`'s body call it. No other call sites change — this is
"move, don't change": `query_tools` / `update_tools` and their tests do not churn.

## ALGORITHM
```
# build_query_body(name, config, backend, backend_name, hint):
resolved_sql = config.resolve_sql(backend_name); params = extract_sql_params(...)
async def body(**kwargs):
    return await execute_and_format(name, resolved_sql, params, backend, config,
                                    filter_kwarg, hint, kwargs)
return body
```

## DATA
No data-shape or signature change. Output byte-identical for every existing tool.

## TESTS (write first)
- Existing `test_query_tools` assertions pass **unchanged** (tool names,
  signatures, execution, max_rows note, filter, formatting) — proves the tail was
  moved without behaviour change.
- One focused unit test of `execute_and_format` (max_rows cap note + filter
  applied) to pin the extracted contract directly.

## LLM PROMPT
> Implement Step 9 from `pr_info/steps/step_9.md` (context in
> `pr_info/steps/summary.md`). Extract the execution+format tail of
> `build_query_body` (max_rows cap + note, filter pop, param strip, log_tool_call,
> execute_query, apply_filter, format_rows) into a new `execute_and_format` helper
> in `query_helpers.py`, and make `build_query_body` delegate to it with its
> registration-time closure otherwise unchanged. This is a behaviour-preserving
> refactor: existing `test_query_tools` assertions must pass unchanged. Add one
> focused `execute_and_format` unit test. Run `mcp__tools-py__run_pylint_check`,
> `mcp__tools-py__run_pytest_check` (`-n auto` + unit markers),
> `mcp__tools-py__run_mypy_check`, and lint-imports/tach; all green. One commit.
