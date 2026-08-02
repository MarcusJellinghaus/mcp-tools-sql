# Step 10 — schema_tools: runtime single-target `connection`/`database` params

See `pr_info/steps/summary.md` → "Tool surface" (decision 16). Fan-out (`*`) is
Step 11; this step does runtime resolution of exactly one target, delegating to
the shared `execute_and_format` core extracted in Step 9.

## WHERE
- `src/mcp_tools_sql/query_helpers.py` (add `build_target_params`,
  `build_schema_body`; both reuse the Step 9 `execute_and_format` core)
- `src/mcp_tools_sql/schema_tools.py` (SchemaTools takes registry + targets)
- `src/mcp_tools_sql/server.py` (pass registry + targets to SchemaTools)
- Tests: `tests/test_schema_tools.py`, `tests/test_server.py`

## WHAT
```python
def build_target_params(targets: ResolvedTargets) -> list[inspect.Parameter]:
    """Keyword-only connection/database params, only when targets.is_multi."""

def build_schema_body(name, config, registry: BackendRegistry,
                      targets: ResolvedTargets, truncation_hint) -> Callable[..., Awaitable[str]]:
    """Resolve ONE target from connection/database kwargs, then delegate to
    execute_and_format (the shared core extracted in Step 9 — no reimplementation
    of the body core)."""

class SchemaTools:
    def __init__(self, registry: BackendRegistry, targets: ResolvedTargets) -> None: ...
```

`build_query_body` already delegates to `execute_and_format` (Step 9), so
`build_schema_body` reuses the same core. Externally `build_query_body` is
unchanged, so `query_tools` / `update_tools` and their tests do not churn.

## HOW
- `build_target_params`: return `[]` unless `targets.is_multi`. When multi, append
  a keyword-only `connection` param **only if `len(connection_names) > 1`**
  (`Literal[*connection_names]`, default = `file_default_connection`) and a
  keyword-only `database` param (`Literal[*database_names]`, **default =
  `None`**). Leaving the default `None` lets `resolve_pinned` fall back to the
  *selected* connection's `default_database` — so `read_tables(connection="other")`
  without an explicit `database` resolves that connection's default instead of
  raising because the file-default connection's default catalog is not a member
  of `other`. Build the enum via `Literal.__getitem__(tuple(names))`.
- `SchemaTools.register`: `sig = build_query_sig_params(config) + build_target_params(targets)`;
  `body = build_schema_body(...)`; `build_tool_fn`; `mcp.add_tool`. When not multi,
  `build_target_params` returns `[]` → signature byte-identical to today.
- `build_schema_body`: pop `connection`/`database` kwargs; resolve one target via
  `targets.resolve_pinned(connection, database)`; get backend from registry;
  compute `resolved_sql = config.resolve_sql(target.backend_name)` (and its
  `sql_params`) per call; then **delegate to `execute_and_format`** (Step 9). No
  max_rows/filter/logging/format logic is reimplemented in `build_schema_body`.
- **Friendly resolve error.** `resolve_pinned` raises `ValueError` when the
  `(connection, database)` pair is invalid — the union `database` enum spans all
  connections, so `database="hr"` under `connection="localdb"` passes JSON-schema
  validation but is not a member of `localdb`. Catch that `ValueError` and
  **return** its message as the tool verdict (e.g. `"database 'hr' is not
  configured for connection 'localdb'. Available: [...]"`) instead of letting it
  surface as an unhandled tool error. `resolve_pinned`'s `ValueError` text must
  already carry the available list (Step 4).

## ALGORITHM (build_schema_body)
```
conn = kwargs.pop("connection", None); db = kwargs.pop("database", None)
try:
    target = targets.resolve_pinned(conn, db)   # db=None -> connection's default
except ValueError as exc:
    return str(exc)                             # friendly call-time verdict
sql = config.resolve_sql(target.backend_name); params = extract_sql_params(sql)
backend = registry.backend_for(target)
return await execute_and_format(name, sql, params, backend, config,
                                filter_kwarg, truncation_hint, kwargs)
# execute_and_format (Step 9) owns: max_rows cap + note, filter pop, param strip,
# log_tool_call, execute_query, apply_filter, format_rows — the single source of
# truth shared with build_query_body.
```

## DATA
Single-target output identical to today (no `_database`, standard footer).

## TESTS (write first)
- Single sqlite target: `read_tables` signature/output byte-identical to current
  tests (regression — reuse existing `test_schema_tools` assertions).
- `build_target_params`: `[]` when not multi; with 2 connections → both params;
  with 1 connection/2 databases → only `database` param; enums list the right
  names; params are `KEYWORD_ONLY`.
- Multi install, `read_tables(schema=..., database="hr")` executes against the
  `(default_conn, hr)` backend (fake registry records the target).
- Multi install with >1 connection: `read_tables(schema=..., connection="other")`
  with no `database` resolves `other`'s `default_database` (default `None` →
  connection default), not the file-default connection's catalog.
- Cross-connection mismatch `read_tables(schema=..., connection="localdb",
  database="hr")` **returns** the friendly verdict string (mentions the
  connection and lists available databases), not an unhandled exception.
- Bad `database` value rejected before execution (invalid enum / resolve error).

## LLM PROMPT
> Implement Step 10 from `pr_info/steps/step_10.md` (context in
> `pr_info/steps/summary.md`). Add `build_target_params` and `build_schema_body`
> (which resolves one target then delegates to the Step 9 `execute_and_format`
> core — no duplicated body logic) to `query_helpers.py`; make `SchemaTools` take
> `(registry, targets)` and assemble each builtin's signature as
> `build_query_sig_params(config) + build_target_params(targets)` with a
> runtime-resolving body (single target, no `*` yet). Params are keyword-only
> `Literal` enums shown only when multi; single-target output stays byte-identical
> and existing `test_schema_tools` assertions must still pass. Update `server`.
> Write tests first (byte-identical single target; conditional params; per-database
> runtime bind; friendly cross-connection verdict). Run pylint, pytest (`-n auto`
> + unit markers), mypy, lint-imports/tach; all green. One commit.
