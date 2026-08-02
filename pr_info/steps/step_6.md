# Step 6 — Server wiring (behaviour unchanged)

See `pr_info/steps/summary.md` → "Two new collaborators".

## WHERE
- `src/mcp_tools_sql/server.py`
- Tests: `tests/test_server.py`

## WHAT
`ToolServer` and `create_server` stop taking `(backend, backend_name)` and take
the resolved targets + registry instead:
```python
class ToolServer:
    def __init__(self, config: QueryFileConfig, targets: ResolvedTargets,
                 registry: BackendRegistry, allow_updates: bool) -> None: ...
```
`run_server` builds them and owns lifecycle:
```python
targets = resolve_targets(qcfg, dbcfg)
registry = BackendRegistry()
try: ToolServer(qcfg, targets, registry, dbcfg.security.allow_updates).run()
finally: registry.close_all()
```

## HOW
This step is a **pure refactor** — behaviour identical for the current
single-target case. `_register_builtin_tools` / `_register_configured_tools`
derive the default backend from the registry and keep passing the existing
`(backend, backend_name)` to each tool class:
```python
default = self._targets.default
backend = self._registry.backend_for(default)
SchemaTools(backend, default.backend_name).register(self._mcp)   # unchanged class
QueryTools(backend, self._config.queries, default.backend_name).register(...)
...
```
Replace the `resolve_connection` import/call with `resolve_targets`. Update the
startup log line to report connection/database counts.

## ALGORITHM
```
targets = resolve_targets(qcfg, dbcfg); registry = BackendRegistry()
default = targets.default; backend = registry.backend_for(default)
register builtin + configured tools using (backend, default.backend_name)
run stdio; finally registry.close_all()
```

## DATA
No public tool-surface change yet; single-target output byte-identical.

## TESTS (write first / update)
- `create_server` / `ToolServer` accept the new signature and register the same
  tool set for a single sqlite target (existing assertions preserved).
- `run_server` calls `registry.close_all()` in `finally` even when `run()` raises
  (monkeypatch `mcp.run` to raise; assert close_all called).
- Startup happy-path still registers builtins + configured tools.

## LLM PROMPT
> Implement Step 6 from `pr_info/steps/step_6.md` (context in
> `pr_info/steps/summary.md`). Refactor `server.py` so `ToolServer`/`create_server`
> take `(config, targets: ResolvedTargets, registry: BackendRegistry,
> allow_updates)`; `run_server` builds them via `resolve_targets` +
> `BackendRegistry`, derives the default target's backend for the (still
> unchanged) tool classes, and calls `registry.close_all()` in `finally`. Behaviour
> must stay identical for a single sqlite target. Update `tests/test_server.py`
> first. Run pylint, pytest (`-n auto` + unit markers), mypy, lint-imports/tach;
> all green. One commit.
