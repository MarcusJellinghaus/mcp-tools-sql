# Step 11 — `validate_sql` / `count_records`: `database` param, per-call dialect

See `pr_info/steps/summary.md` → "Tool surface" (decision 12). No `database="*"`
for these tools.

## WHERE
- `src/mcp_tools_sql/validation_tools.py`, `src/mcp_tools_sql/count_tools.py`
- `src/mcp_tools_sql/server.py` (pass registry + targets)
- Tests: `tests/test_validation_tools.py`, `tests/test_count_tools.py`,
  `tests/test_server.py`

## WHAT
```python
class ValidationTools:
    def __init__(self, registry: BackendRegistry, targets: ResolvedTargets) -> None: ...
class CountTools:
    def __init__(self, registry: BackendRegistry, targets: ResolvedTargets) -> None: ...
```
Both tools resolve backend + dialect **per call** from optional keyword-only
`connection`/`database` params (conditional, `Literal` enums, no `"*"`).

## HOW
Assemble each tool via `build_tool_fn` so the conditional params can be added:
- base params `[sql, params, return_plan]` (validate) / `[sql, params]` (count)
  plus `build_target_params_no_star(targets)` (like `build_target_params` but the
  `database` enum omits `"*"`). Reuse `build_target_params` with a `star: bool=False`
  flag rather than duplicating.
  - **Dependency on Step 10:** adding a `star=False` default flips the previous
    unconditional `"*"` behaviour, so the Step 10 `schema_tools` caller
    `build_target_params(targets)` **must be updated to `build_target_params(targets,
    star=True)`** in this step, or `database="*"` fan-out silently regresses.
    validate/count pass `star=False`.
- Core body signature: `async def core(sql, params, return_plan=..., *, connection=None, database=None)`.
- Inside: `target = targets.resolve_pinned(connection, database)` (catch its
  `ValueError` and **return** the message as the verdict — same friendly
  cross-connection error as `build_schema_body`, Step 9);
  `backend = registry.backend_for(target)`; `dialect = to_dialect(target.backend_name)`;
  then the existing preflight / `_explain` / `read_only_violation` /
  `build_count_query` logic using that `backend` + `dialect`.
- `_explain(backend, backend_name, sql, params)` already takes backend_name — pass
  `target.backend_name`.

## ALGORITHM (validate core)
```
try:
    target = targets.resolve_pinned(connection, database)   # db=None -> conn default
except ValueError as exc:
    return str(exc)                          # friendly cross-connection verdict
dialect = to_dialect(target.backend_name)
verdict = _preflight(sql, params, dialect);  if verdict: return verdict
plan = _explain(registry.backend_for(target), target.backend_name, sql, params)
return "Valid." (+ plan if return_plan)
```

## DATA
Single-target: signatures byte-identical to today (`build_target_params` → `[]`).
Multi: `connection?`/`database?` keyword-only enums added.

## TESTS (write first)
- Single sqlite target: `validate_sql`/`count_records` signatures + behaviour
  byte-identical to current tests.
- Multi install: `database` param present (enum has no `"*"`); passing
  `database="hr"` resolves dialect + backend for that target (fake registry).
- Multi install: `build_target_params(targets, star=True)` still yields the `"*"`
  member (Step 10 fan-out) while `star=False` omits it (regression guard for the
  shared flag).
- Cross-connection mismatch (`connection="localdb", database="hr"`) **returns**
  the friendly verdict string, not an unhandled exception.
- `count_records` still rejects non-read-only SQL and CTE-on-tsql as before.

## LLM PROMPT
> Implement Step 11 from `pr_info/steps/step_11.md` (context in
> `pr_info/steps/summary.md`). Make `ValidationTools`/`CountTools` take
> `(registry, targets)` and assemble their tools via `build_tool_fn` with base
> params plus `build_target_params(targets, star=False)`; resolve backend +
> `to_dialect` per call from `connection`/`database` kwargs (default → default
> target). Keep all existing preflight/explain/read-only/count logic. Update
> `server`. Single-target signatures/behaviour must stay byte-identical. Write
> tests first. Run pylint, pytest (`-n auto` + unit markers), mypy,
> lint-imports/tach; all green. One commit.
