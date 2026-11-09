# Step 8 – Wire single-target query and schema tools

## LLM prompt
Read `pr_info/steps/summary.md` (sections 4, 5, 6 and 7) and this file.
Implement step 8 only, test-first: `execute_and_format` reads through
`iter_readonly_batches` → `collect` → `render_limited`; `LimitsConfig` is passed
`ToolServer` → `SchemaTools` / `QueryTools` → the body builders; both
`_TRUNCATION_HINT` constants are removed. Fan-out (`database="*"`) stays on the
old path until step 9. Run pylint, pytest (`-n auto`), mypy, lint-imports;
format; one commit.

## WHERE
- `src/mcp_tools_sql/query_helpers.py`
- `src/mcp_tools_sql/query_tools.py`
- `src/mcp_tools_sql/schema_tools.py`
- `src/mcp_tools_sql/server.py`
- Tests: `tests/test_query_limits_tools.py` (new); update existing assertions
  in `tests/test_query_tools.py`, `tests/test_schema_tools.py`,
  `tests/test_query_helpers.py` (old `Showing N of M rows.` / hint wording,
  `build_query_body(..., truncation_hint)` calls)

## WHAT
```python
# query_helpers.py
async def execute_and_format(
    name: str,
    resolved_sql: str,
    sql_params: set[str],
    backend: DatabaseBackend,
    config: QueryConfig,
    filter_kwarg: str | None,
    kwargs: dict[str, Any],
    *,
    limits: LimitsConfig,
    builtin: bool,
    timeout_seconds: int,
    enforces_counting: bool,   # backend_name == "sqlite"
) -> str: ...

def build_query_body(
    name, config, backend, backend_name, *,
    timeout_seconds: int, limits: LimitsConfig | None = None,
) -> Callable[..., Awaitable[str]]: ...        # builtin=False

def build_schema_body(
    name, config, registry, targets, *, limits: LimitsConfig | None = None,
) -> Callable[..., Awaitable[str]]: ...        # builtin=True

# query_tools.py / schema_tools.py
QueryTools(registry, targets, queries, *, limits: LimitsConfig | None = None)
SchemaTools(registry, targets, *, limits: LimitsConfig | None = None)
```

## HOW
- `None` → `LimitsConfig()` in builders and toolkits, so existing tests that
  construct them without limits keep working.
- `QueryTools.register` passes `timeout_seconds=target.config.query_timeout_seconds`.
  The pinned schema path passes `target.config.query_timeout_seconds`.
- `enforces_counting=(backend_name == "sqlite")`: `build_query_body` uses its
  `backend_name`, the pinned schema path `target.backend_name`. It becomes
  `Source.enforces_counting`, so a SQL Server timeout is never labelled
  `counting stopped`.
- `ToolServer._register_builtin_tools` / `_register_configured_tools` pass
  `limits=self._config.limits`.
- Filtering reuses `apply_filter` per batch:
  `filter_rows=lambda b: apply_filter(b, config.filter_column, pattern)` when a
  filter kwarg exists, else the identity default.
- `has_sql_params=bool(sql_params)`; `max_rows_hard = max(config.max_rows_hard, MAX_ROWS_MIN)`.
- `rec.record(rows=result.total, cols=len(result.rows[0]) if result.rows else 0)`.
- Remove `QueryTools._TRUNCATION_HINT`, `SchemaTools._TRUNCATION_HINT` and the
  `truncation_hint` parameters of `execute_and_format` / `build_query_body`.
  `build_schema_body` keeps passing a hint to `format_fanout_rows` internally
  until step 9 (inline the old `"Use filter to narrow."` string there).

## ALGORITHM
```
requested, note = _cap_max_rows(config, kwargs.pop("max_rows", default))
pattern = kwargs.pop(filter_kwarg) if filter_kwarg; stripped = declared SQL params only
source = Source(database="", open=lambda dl: backend.iter_readonly_batches(resolved_sql, stripped or None, counting=dl),
                enforces_counting=enforces_counting)
result = collect([source], max_rows=requested, limits=limits,
                 counting_seconds=counting_time_limit(timeout_seconds), filter_rows=...)
return render_limited(result, ..., fanout=False, ...) + note
```

## DATA
Tool text as produced by `render_limited`, plus the existing cap note.

## Tests (write first)
`tests/test_query_limits_tools.py` (SQLite fixtures, tools registered on a
`FastMCP` or bodies called directly, as in existing tests):
- Configured query with SQL params, `max_rows` truncation: total and effective
  `max_rows_hard` named; when requested `max_rows ≥ max_rows_hard` (capped) only
  `refine parameters`.
- Built-in `read_columns` on the 150-column fixture: `showing 100 of 150 rows
  (max_rows=100 reached)`.
- SQLite `read_tables` (declared `schema`, not bound in its SQL): no parameter
  phrase on truncation; on timeout no hint.
- Configured query with `filter_column` and no placeholders: `narrow with
  <col>_filter` on truncation; on timeout no hint.
- Char budget: small `[limits] max_output_chars` → table length (text before the
  first `\n\n[Output truncated`) ≤ the limit, message present, including a
  query whose column header is wider than every cell in it; cell cap with
  marker and `Long values were cut at N chars.`; first row wider than the
  budget → 0 rows + wider-than-limit message.
- `*_filter` whose matches are beyond the first raw batch (> 500 raw rows) →
  matches found, exact count.
- Timeout (`query_timeout_seconds=1`, configured query that returns no rows
  until the timeout fires, with a bound `:param`, e.g.
  `WITH RECURSIVE c(x) AS (SELECT :start UNION ALL SELECT x+1 FROM c) SELECT count(*) FROM (SELECT x FROM c LIMIT 500000000)`):
  asserts exactly `Query aborted after 1 s (statement timeout). Use more
  selective parameters.` (a streaming query would fill the display set first
  and end with `N+ (counting stopped)` instead); built-in `read_schemas` timeout (fake backend raising
  `QueryTimeoutError`) → exactly `Query aborted after N s (statement timeout).`
- Statement timeout after some matched rows, display incomplete (fake backend
  yielding one batch then raising `QueryTimeoutError`) → rows shown with
  `N+ (stopped: statement timeout)`.
- Counting time limit during counting (fake backend + patched clock) → rows
  shown with `N+` and `counting stopped`.
- `ToolServer` passes `config.limits` (a `[limits]` value reaches the tools).
