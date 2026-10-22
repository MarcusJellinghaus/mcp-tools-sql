# Step 7 — Enable `UP` (pyupgrade); keep the `tool` CLI working with `X | None`

## LLM prompt
> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_7.md`.
> Follow the order below exactly (probe before the conversion, failing test
> before the fix). Delete `.scratch/` before committing. Make exactly one
> commit.

## WHERE
- `pyproject.toml`
- `src/mcp_tools_sql/cli/commands/tool_args.py` — `_unwrap_annotation`
- `tests/cli/test_tool_args.py` — new test
- Files converted by ruff: `query_helpers.py`, `update_tools.py`,
  `count_tools.py`, `validation_tools.py`, `summarize/tools.py`,
  `config/models.py`, `tests/cli/test_tool_args.py`,
  `tests/test_dynamic_tool_registration.py`, other tests with `Optional[...]`
- Temporary: `.scratch/test_schema_probe.py`, `.scratch/schemas_before.json`

## Order
### 7.1 Schema probe (before any change)
Create `.scratch/test_schema_probe.py`, a single pytest test:
```
build QueryFileConfig.model_validate({...}) with:
    one query: params int(desc, optional), float(no desc, optional),
               bool(optional), str(required); filter_column="name"
    one update: key int, fields: int optional, str required
build multi targets via tests.target_helpers.make_target:
    2 connections, first with 2 databases  (exercises Literal / Optional[db_enum])
registry = BackendRegistry subclass whose backend_for returns an
    unconnected SQLiteBackend(ConnectionConfig(backend="sqlite", path=":memory:"))
server = ToolServer(qcfg, targets, registry, allow_updates=True); server.register_all()
dump = json.dumps({t.name: t.parameters for t in server.mcp._tool_manager.list_tools()}, indent=2)
if .scratch/schemas_before.json missing: write dump
else: assert dump == file contents
```
No `sort_keys` — key and `anyOf` order must be compared as-is.
Run: `run_pytest_check(extra_args=["-p","no:cacheprovider",".scratch/test_schema_probe.py"])`.
Confirm `schemas_before.json` exists and contains the `update_*`, query and
multi-target (`database`/`connection` enum) schemas.

### 7.2 Failing test first (TDD)
Add to `tests/cli/test_tool_args.py` (import `_unwrap_annotation` alongside the
existing imports):
```python
def test_unwrap_annotation_accepts_pep604_optional() -> None:
    """`Annotated[int | None, Field(...)]` unwraps to `int` plus its description."""
    base, description = _unwrap_annotation(
        Annotated[int | None, Field(description="Count")]
    )
    assert base is int
    assert description == "Count"
```
Run it; it must fail (base is `int | None`).

### 7.3 Fix `_unwrap_annotation`
```python
import types
...
if get_origin(annotation) in (Union, types.UnionType):
```
Update the docstring's first line only if needed ("``Optional``/``X | None``").
Run the new test → passes.

### 7.4 Convert
1. `pyproject.toml`: append `"UP"` to `select`.
2. `run_ruff_fix(select=["UP", "F401"], target_directories=["src","tests","tools"])`.
3. Remove every leftover `# noqa: UP007` (12 in src, 6 in tests). Verify with
   `search_files(pattern="noqa: UP007")` → no matches.
4. `run_ruff_check(select=["UP045"], target_directories=["src","tests","tools"])`
   → clean; convert any leftover by hand.
5. `run_format_code` (black may re-join `query_helpers.py` ~192-193).

### 7.5 Probe again, then delete it
Re-run the probe. It must pass (byte-identical schemas). If it fails, write
one line to `pr_info/.blocked.txt` naming the first differing tool, and stop
(do not commit). On success: `delete_directory(".scratch", recursive=True)`.

## DATA
`_unwrap_annotation(annotation) -> tuple[Any, str | None]` — unchanged
signature. For `X | None` it now returns `X`, as it already did for
`Optional[X]`.

## Guards after this step
- `test_optional_int_param_omittable_and_parsed` now uses `int | None`
  (converted by ruff) and fails without 7.3: it is the end-to-end guard.
- `test_unwrap_annotation_accepts_pep604_optional` is the unit guard.

## Verification
- `run_ruff_check(target_directories=["src","tests","tools"])` → clean.
- pylint, mypy `--strict`, full pytest (`-n auto`) green.
- `.scratch/` does not exist.

## Commit
`ruff: enable UP; accept types.UnionType in tool CLI annotation unwrapping`
