# Step 5 — `BackendRegistry`

See `pr_info/steps/summary.md` → "Two new collaborators".

## WHERE
- `src/mcp_tools_sql/backends/registry.py` (new)
- Tests: `tests/backends/test_registry.py`

## WHAT
```python
class BackendRegistry:
    def __init__(self) -> None: ...
    def backend_for(self, target: ResolvedTarget) -> DatabaseBackend: ...
    def close_all(self) -> None: ...
```
Lazily instantiates one `DatabaseBackend` per `(connection, database)` key via
`create_backend(target.config)`, caches it, and returns the cached instance on
repeat calls. `close_all()` closes every instantiated backend, swallowing
per-backend close errors so one failure does not skip the rest.

## HOW
`from mcp_tools_sql.backends.base import DatabaseBackend, create_backend`.
Registry lives in the `backends` (infrastructure) package — it may import
`config` (for the `ResolvedTarget` type) and `backends.base`. No tach/importlinter
change needed (submodule of `backends`; `create_backend` does the concrete-backend
imports itself, so siblings are not imported directly).

## ALGORITHM
```
key = (target.connection, target.database)
if key not in self._backends:
    self._backends[key] = create_backend(target.config)
return self._backends[key]
# close_all: for b in self._backends.values(): try: b.close() except Exception: pass
```

## DATA
`_backends: dict[tuple[str, str], DatabaseBackend]`. `backend_for` returns a
`DatabaseBackend` (lazy `connect()` still owned by the backend on first query).

## TESTS (write first)
- `backend_for` on the same target twice returns the **same** instance (cached).
- Different targets → different instances (use two sqlite paths).
- `close_all` calls `close()` on all created backends (assert via a fake backend
  or by re-query raising after close for sqlite).
- `close_all` continues past a backend whose `close()` raises (fake backend).
- `backend_for` does not connect eagerly (no file/network access until a query).

## LLM PROMPT
> Implement Step 5 from `pr_info/steps/step_5.md` (context in
> `pr_info/steps/summary.md`). Create `backends/registry.py` with `BackendRegistry`
> (`backend_for` lazily `create_backend`+cache by `(connection, database)`;
> `close_all` closes all, swallowing per-backend errors). Write tests first
> (caching identity, distinct targets, close-all, error resilience, no eager
> connect). Run pylint, pytest (`-n auto` + unit markers), mypy, and
> `mcp__tools-py__run_lint_imports_check` / `run_tach_check` to confirm boundaries
> hold. All green. One commit.
