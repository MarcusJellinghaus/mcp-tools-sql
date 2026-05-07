# Step 4 — Add `filter_column`; auto-inject `max_rows` and `<col>_filter` params

## LLM Prompt

> Read `pr_info/steps/summary.md`, then implement Step 4 from
> `pr_info/steps/step_4.md`: add `QueryConfig.filter_column`, change
> `tool_builder.build_tool_fn` so that `max_rows` and `<filter_column>_filter`
> are no longer expected in `params` (they are injected implicitly), and
> update `default_queries.toml` to use `filter_column = "name"` for
> `read_columns` instead of explicit `params.filter` / `params.max_rows`
> blocks. Update tests so the old `filter` parameter becomes `name_filter`.
> Use TDD. MCP tools only. Run pylint, mypy, pytest, lint-imports, tach.
> One commit when all pass.

## WHERE

- `src/mcp_tools_sql/config/models.py` — add `filter_column: str = ""`
- `src/mcp_tools_sql/tool_builder.py` — change signature build + body
- `src/mcp_tools_sql/default_queries.toml` — `read_columns`: drop
  `params.filter` and `params.max_rows`; add `filter_column = "name"`
- `src/mcp_tools_sql/cli/commands/verify.py` — remove entirely the
  `_LEGITIMATE_NON_SQL_PARAMS` exclusion list (no longer needed)
- `tests/test_default_queries.py` — adjust assertions, and **delete two
  now-obsolete test methods entirely**:
  - `test_read_columns_has_filter_param` — its sole assertions
    (`"filter" in columns_config.params`) become invalid once
    `params.filter` is removed in this step. Coverage of the new
    `filter_column` configuration is already provided by the
    implicit-filter-injection tests added in Step 6.
  - `test_read_columns_has_max_rows_param` — its sole `params`-side
    assertions become invalid once `params.max_rows` is removed in this
    step. The field-rename assertion `columns_config.max_rows_default ==
    100` is already covered by Step 2's `test_smoke.py` and
    `test_loader.py` updates.
- `tests/test_schema_tools.py` — `filter` → `name_filter`
- `tests/cli/test_verify.py` — rename
  `test_verify_queries_accepts_filter_and_max_rows_as_non_sql_params` to
  `test_verify_queries_rejects_filter_and_max_rows_as_non_sql_params`.
  Invert the assertions: `result["with_filter.params"]["ok"] is False` and
  the error message contains `"not used in SQL"`. This converts the existing
  allow-list test into a regression guard for the new stricter behavior.
- `tests/config/test_models.py` — test for `filter_column` default

## WHAT

```python
class QueryConfig(BaseModel):
    description: str = ""
    sql: str
    params: dict[str, QueryParamConfig] = {}
    max_rows_default: int = 100
    max_rows_hard: int | None = None
    filter_column: str = ""
    backends: dict[str, BackendQueryConfig] = {}
```

`build_tool_fn` (revised):

```python
def build_tool_fn(name, config, backend, backend_name) -> Callable[..., Any]:
    resolved_sql = config.resolve_sql(backend_name)
    sql_params = extract_sql_params(resolved_sql)
    filter_kwarg = f"{config.filter_column}_filter" if config.filter_column else None

    async def _tool_fn(**kwargs) -> str:
        requested = kwargs.pop("max_rows", config.max_rows_default)
        filter_pat = kwargs.pop(filter_kwarg, None) if filter_kwarg else None
        note = ""
        if requested > config.max_rows_hard:
            note = (f"\n\nRequested max_rows={requested} exceeds hard "
                    f"limit {config.max_rows_hard}; capped at "
                    f"{config.max_rows_hard}.")
            requested = config.max_rows_hard
        stripped = {k: v for k, v in kwargs.items() if k in sql_params}
        async with log_tool_call(name, stripped, sql=resolved_sql) as rec:
            rows = backend.execute_query(resolved_sql, stripped or None)
            if filter_kwarg:
                rows = apply_filter(rows, config.filter_column, filter_pat)
            rec.record(rows=len(rows), cols=len(rows[0]) if rows else 0)
            return format_rows(rows, requested) + note
    ...
```

## HOW

- Signature construction loop now only iterates user-declared params
  (no `max_rows` / `filter` special-cases).
- After the loop, append:
  - `max_rows: int | None` with default `config.max_rows_default`,
    description `"Maximum rows to return"`.
  - When `config.filter_column` is non-empty, append
    `<filter_column>_filter: str | None` with default `None`, description
    `f"Glob pattern (case-insensitive) on the {config.filter_column} column"`.
- Builder is still prefix-agnostic; schema tools keep using bare names.
- `format_rows` still uses its default hint at this step (Step 4 does not
  change the truncation_hint — schema tools keep `"Use filter to narrow."`,
  query tools start passing the LLM-friendly hint in Step 6).
- After this change, a TOML that mistakenly declares `filter` or `max_rows`
  in a `[queries.<name>.params]` block will fail
  `_check_params_well_formed` with `"Config params [...] not used in SQL"`.
  This is the desired behavior — those parameters are now reserved /
  auto-injected and must not be user-declared.

## ALGORITHM

See pseudocode in WHAT. Two extra `kwargs.pop` calls + one conditional
`apply_filter`.

## DATA

- New TOML field: `filter_column = "name"` at the query level (sibling of
  `sql`, `params`, `max_rows_default`).
- `read_columns` MCP tool's `filter` parameter renames to `name_filter`
  (consequence of the auto-generation rule). Documented as a pre-1.0
  break in the issue (decision #19).

## TDD Tests

1. `tests/config/test_models.py::test_filter_column_default_empty`
2. `tests/test_default_queries.py` — `read_columns.filter_column == "name"`
   and the obsolete `params.filter` / `params.max_rows` assertions are
   removed; `params.schema` and `params.table` remain
3. `tests/test_schema_tools.py::test_read_columns_with_filter` and
   `test_read_columns_filter_no_match` — call with `name_filter` instead
   of `filter`
4. `tests/test_tool_builder.py::test_build_fn_injects_max_rows`
5. `tests/test_tool_builder.py::test_build_fn_injects_filter_when_set`
6. `tests/test_tool_builder.py::test_build_fn_no_filter_when_unset`

## Verification

- pylint, mypy, pytest, lint-imports, tach

## Commit

One commit.
