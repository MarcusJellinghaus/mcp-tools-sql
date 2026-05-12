# Step 1 — Refactor `tool_builder.py` into a Pure Assembler

## Goal

Make `build_tool_fn` tool-type-agnostic so `UpdateTools` can call the same
assembler in a later step. Move query-specific helpers
(`extract_sql_params`, `apply_filter`, `max_rows` clamp, `<col>_filter`
injection) directly into `query_tools.py`. Add a module-level `_UNSET`
sentinel for update bodies to use later.

**No behaviour change** — every existing test in `test_tool_builder.py`,
`test_query_tools.py`, `test_schema_tools.py`, `test_server.py`, and
`cli/test_verify.py` continues to pass after this step.

## WHERE

- `src/mcp_tools_sql/tool_builder.py` — gutted to the assembler + sentinel
- `src/mcp_tools_sql/query_tools.py` — receives the helpers + new body builder
- `src/mcp_tools_sql/schema_tools.py` — `SchemaTools.register` builds its own
  sig_params + body via the new helpers
- `src/mcp_tools_sql/cli/commands/verify.py` — update import of
  `extract_sql_params` to its new location (`query_tools`)
- `tests/test_tool_builder.py` — adjusted to test the new assembler signature
- `tests/test_query_tools.py` — adjusted to import helpers from `query_tools`
- `tests/test_schema_tools.py` — adjusted likewise

## WHAT

### `tool_builder.py`

```python
_UNSET: Any = object()  # exported sentinel for "field not passed"

def build_tool_fn(
    name: str,
    sig_params: list[inspect.Parameter],
    body: Callable[..., Awaitable[str]],
    doc: str,
) -> Callable[..., Any]: ...
```

Returns a closure with `__signature__`, `__name__`, `__doc__` wired up. The
closure is `async def _tool_fn(**kwargs)` that simply awaits `body(**kwargs)`.

### `query_tools.py`

```python
def extract_sql_params(sql: str) -> set[str]: ...
def apply_filter(rows: list[dict], column: str, pattern: str | None) -> list[dict]: ...

def _build_query_body(
    name: str,
    config: QueryConfig,
    backend: DatabaseBackend,
    backend_name: str,
    truncation_hint: str,
) -> Callable[..., Awaitable[str]]: ...

def _build_query_sig_params(config: QueryConfig) -> list[inspect.Parameter]: ...
```

`QueryTools.register` and `SchemaTools.register` both call
`_build_query_sig_params(config)` + `_build_query_body(...)` then hand the
results to the shared `build_tool_fn`.

## HOW

- `tool_builder.py` no longer imports `QueryConfig`, `format_rows`, or
  `log_tool_call` — those move with the body into `query_tools.py`.
- `query_tools.py` imports `build_tool_fn` and `_UNSET` from `tool_builder`.
- `schema_tools.py` imports the helpers + body builder from `query_tools.py`.
- `cli/commands/verify.py`: replace
  `from mcp_tools_sql.tool_builder import extract_sql_params` with
  `from mcp_tools_sql.query_tools import extract_sql_params`.

## ALGORITHM — new `build_tool_fn`

```
async def _tool_fn(**kwargs):
    return await body(**kwargs)
_tool_fn.__signature__ = inspect.Signature(sig_params)
_tool_fn.__name__ = name
_tool_fn.__doc__ = doc
return _tool_fn
```

## ALGORITHM — `_build_query_body` (existing logic, now in `query_tools.py`)

```
filter_kwarg = f"{config.filter_column}_filter" if config.filter_column else None
sql_params = extract_sql_params(config.resolve_sql(backend_name))

async def body(**kwargs):
    requested, note = clamp_max_rows(kwargs, config)
    filter_pattern = kwargs.pop(filter_kwarg, None) if filter_kwarg else None
    stripped = {k: v for k, v in kwargs.items() if k in sql_params}
    async with log_tool_call(name, stripped, sql=resolved_sql) as rec:
        rows = backend.execute_query(resolved_sql, stripped or None)
        if filter_kwarg: rows = apply_filter(rows, config.filter_column, filter_pattern)
        rec.record(rows=len(rows), cols=len(rows[0]) if rows else 0)
        return format_rows(rows, requested, truncation_hint=truncation_hint) + note
```

## ALGORITHM — `_build_query_sig_params` (existing logic, now in `query_tools.py`)

```
sig_params = []
for p in config.params.values():
    sig_params.append(make_param(p, default=empty if p.required else None))
sig_params.append(make_param("max_rows", default=config.max_rows_default, annotation=int))
if config.filter_column:
    sig_params.append(make_param(f"{config.filter_column}_filter", default=None, annotation=Optional[str]))
return sig_params
```

## DATA

- `build_tool_fn` returns `Callable[..., Awaitable[str]]` (an async tool fn
  with dynamic signature) — unchanged from today's behaviour.
- `extract_sql_params` returns `set[str]` — unchanged.
- `apply_filter` returns `list[dict[str, Any]]` — unchanged.
- `_UNSET` is module-level `Any`, identity-comparable via `is _UNSET`.

## Tests

TDD: write/adjust tests **before** changing implementation files.

- `tests/test_tool_builder.py`:
  - Replace existing `TestBuildFnImplicitParams` / `TestBuildFnFilterBehavior`
    tests with assembler-shape tests:
    - `build_tool_fn` wires `__name__`, `__doc__`, `__signature__` correctly.
    - Passing an empty body that returns a fixed string round-trips.
  - Keep `TestExtractSqlParams` / `TestApplyFilter` but update imports to
    `from mcp_tools_sql.query_tools import extract_sql_params, apply_filter`.
  - Add: `_UNSET` is importable from `mcp_tools_sql.tool_builder` and is
    not `None` / not equal to itself by value (identity-comparable only).

- `tests/test_query_tools.py` / `tests/test_schema_tools.py`:
  - Update any direct imports from `tool_builder` for the moved helpers.
  - All existing behaviour assertions stay green unchanged.

- `tests/cli/test_verify.py`:
  - No test changes expected; the import update in `verify.py` is internal.

## LLM Prompt

> Read `pr_info/steps/summary.md` (full file) and `pr_info/steps/step_1.md`.
> Implement Step 1 only: refactor `src/mcp_tools_sql/tool_builder.py` into a
> pure assembler `build_tool_fn(name, sig_params, body, doc)` with a
> module-level `_UNSET = object()` sentinel; move `extract_sql_params`,
> `apply_filter`, and the query-specific body/signature builders into
> `src/mcp_tools_sql/query_tools.py`. Update `QueryTools.register` and
> `SchemaTools.register` to build their own `sig_params` + body and call
> the assembler. Update the import of `extract_sql_params` in
> `src/mcp_tools_sql/cli/commands/verify.py`. Follow TDD: adjust tests in
> `tests/test_tool_builder.py`, `tests/test_query_tools.py`, and
> `tests/test_schema_tools.py` **before** changing implementation. No
> behaviour change is intended — all existing tests must pass. Run
> `mcp__tools-py__run_pylint_check`, `mcp__tools-py__run_pytest_check`
> (with the fast unit-test marker exclusion), and
> `mcp__tools-py__run_mypy_check`. Make exactly one commit when green.
