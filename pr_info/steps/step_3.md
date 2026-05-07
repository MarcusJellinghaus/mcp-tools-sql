# Step 3 — Create `tool_builder.py`; extract helpers; add layer

## LLM Prompt

> Read `pr_info/steps/summary.md`, then implement Step 3 from
> `pr_info/steps/step_3.md`: create the new `mcp_tools_sql.tool_builder`
> module by mechanically moving `extract_sql_params`, `_apply_filter` (now
> column-parameterized), and `_build_tool_fn` out of `schema_tools.py`. Update
> `schema_tools.py`, `cli/commands/verify.py`, and tests to import from
> `tool_builder`. Add the new layer to `.importlinter` and `tach.toml`.
> Behaviour must be unchanged. Use TDD (move existing tests, do not duplicate).
> MCP tools only. Run pylint, mypy, pytest, lint-imports, and tach checks.
> One commit when all pass.

## WHERE

- `src/mcp_tools_sql/tool_builder.py` — **create**
- `src/mcp_tools_sql/schema_tools.py` — drop the moved helpers; import them
- `src/mcp_tools_sql/cli/commands/verify.py` — import `extract_sql_params`
  from `tool_builder`
- `.importlinter` — add `mcp_tools_sql.tool_builder` between the tool group
  and the infrastructure layer
- `tach.toml` — declare `mcp_tools_sql.tool_builder` module + dependencies;
  update tool modules to depend on it
- `tests/test_tool_builder.py` — **create**: move `TestExtractSqlParams` and
  `TestApplyFilter` here from `tests/test_schema_tools.py`
- `tests/test_schema_tools.py` — drop the moved test classes; update imports
  for `_build_tool_fn` to come from `tool_builder`

## WHAT

```python
# src/mcp_tools_sql/tool_builder.py

def extract_sql_params(sql: str) -> set[str]: ...

def apply_filter(
    rows: list[dict[str, Any]],
    column: str,
    pattern: str | None,
) -> list[dict[str, Any]]: ...

def build_tool_fn(
    name: str,
    config: QueryConfig,
    backend: DatabaseBackend,
    backend_name: str,
) -> Callable[..., Any]: ...
```

## HOW

- `_apply_filter` becomes `apply_filter(rows, column, pattern)`. The schema
  tools' current `_build_tool_fn` calls `apply_filter(rows, "name", pat)` —
  hardcoded "name" preserved here; Step 4 generalizes it.
- `build_tool_fn` body and signature-construction logic are byte-for-byte the
  same as today's `schema_tools._build_tool_fn` (including the special-cases
  for `max_rows` and `filter` params, the clamp added in Step 2, and the
  `format_rows` call). Pure mechanical extract.
- `schema_tools.py` shrinks to: `load_default_queries`,
  `register_builtin_tools` (still a function), and re-imports of the helpers
  via `from mcp_tools_sql.tool_builder import ...` so existing tests/users
  that import them from `schema_tools` keep working until Step 4/5.

### `.importlinter` change

```ini
layers =
    mcp_tools_sql.main
    mcp_tools_sql.cli
    mcp_tools_sql.server
    mcp_tools_sql.schema_tools | mcp_tools_sql.query_tools | mcp_tools_sql.update_tools | mcp_tools_sql.validation_tools
    mcp_tools_sql.tool_builder
    mcp_tools_sql.backends | mcp_tools_sql.formatting | mcp_tools_sql.tool_logging
    mcp_tools_sql.config
    mcp_tools_sql.utils
```

### `tach.toml` change

- New `[[modules]] path = "mcp_tools_sql.tool_builder"` in
  `tool_implementation` layer with `depends_on` of `backends`, `config`,
  `formatting`, `tool_logging`, `utils`.
- Append `{ path = "mcp_tools_sql.tool_builder" }` to the `depends_on` list of
  `mcp_tools_sql.schema_tools`, `mcp_tools_sql.query_tools`,
  `mcp_tools_sql.update_tools`, `mcp_tools_sql.validation_tools`.

(The existing `tool_implementation` layer holds both the tool modules and
`tool_builder`. Direction is enforced via the `depends_on` lists.)

## ALGORITHM

No algorithmic change — mechanical move.

## DATA

No structural change. Public API of moved helpers stays callable.

## TDD Tests

- Move `TestExtractSqlParams` (4 tests) and `TestApplyFilter` (4 tests) from
  `tests/test_schema_tools.py` to `tests/test_tool_builder.py`.
- `TestApplyFilter` updates to pass an explicit column argument: e.g.
  `apply_filter(rows, "name", "user_*")`.
- `tests/test_schema_tools.py` keeps its MCP-protocol integration tests.
- All passing tests must continue passing.

## Verification

- `mcp__tools-py__run_pylint_check`
- `mcp__tools-py__run_mypy_check`
- `mcp__tools-py__run_pytest_check(extra_args=["-n", "auto", ...])`
- `mcp__tools-py__run_lint_imports_check`
- `mcp__tools-py__run_tach_check`

## Commit

One commit.
