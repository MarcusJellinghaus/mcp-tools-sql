# Step 7 — Pinned per-target backend for `query_*` / `update_*`

See `pr_info/steps/summary.md` → "Tool surface" (decisions 6, 11, 15).

## WHERE
- `src/mcp_tools_sql/query_tools.py`, `src/mcp_tools_sql/update_tools.py`
- `src/mcp_tools_sql/server.py` (pass registry + targets to these classes)
- Tests: `tests/test_query_tools.py`, `tests/test_update_tools.py`,
  `tests/test_server.py`

## WHAT
`QueryTools` / `UpdateTools` take the registry + targets and select each tool's
backend at **registration** from its pinned `(connection, database)`:
```python
class QueryTools:
    def __init__(self, registry: BackendRegistry, targets: ResolvedTargets,
                 queries: dict[str, QueryConfig]) -> None: ...
class UpdateTools:
    def __init__(self, registry: BackendRegistry, targets: ResolvedTargets,
                 updates: dict[str, UpdateConfig]) -> None: ...
```
Body shape unchanged (single bound backend per tool).

## HOW
Per query/update, resolve the pinned target once and fetch its backend:
```python
target = targets.resolve_pinned(cfg.connection or None, cfg.database or None)
backend = registry.backend_for(target)
body = build_query_body(name, config, backend, target.backend_name, hint)   # query
# update: _build_update_body(name, cfg, qualified, backend); backend_name unused
```
`server._register_configured_tools` passes `(self._registry, self._targets, ...)`.
`resolve_pinned` raising `ValueError` on a bad pinned target surfaces at
registration (fail fast), consistent with existing name-validation errors.

## ALGORITHM
```
for name, cfg in items:
    target = targets.resolve_pinned(cfg.connection or None, cfg.database or None)
    backend = registry.backend_for(target)
    build sig + body bound to backend/target.backend_name; mcp.add_tool(...)
```

## DATA
No signature change to the generated `query_*` / `update_*` tools.

## TESTS (write first)
- A query with no pinned fields binds to the default target's backend.
- A query pinned to a second connection binds to that connection's backend (use a
  fake registry recording which target `backend_for` was called with).
- A query pinned to `database="hr"` resolves `(default_conn, hr)`.
- Invalid pinned target → `ValueError` at `register()`.
- Existing single-target `test_query_tools`/`test_update_tools` assertions hold
  (tool names, signatures, execution) with the new constructor.

## LLM PROMPT
> Implement Step 7 from `pr_info/steps/step_7.md` (context in
> `pr_info/steps/summary.md`). Change `QueryTools`/`UpdateTools` to take
> `(registry, targets, queries|updates)` and resolve each tool's pinned target via
> `targets.resolve_pinned(cfg.connection or None, cfg.database or None)`, binding
> the registry backend at registration; keep body shapes unchanged. Update
> `server._register_configured_tools`. Write tests first (default bind, per-connection
> bind, per-database bind, invalid-pin error, existing single-target behaviour).
> Run pylint, pytest (`-n auto` + unit markers), mypy, lint-imports/tach; all green.
> One commit.
