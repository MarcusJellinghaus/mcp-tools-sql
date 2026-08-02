# Step 8 — `read_databases` tool (config-only)

See `pr_info/steps/summary.md` → "Tool surface" (decision 13).

## WHERE
- `src/mcp_tools_sql/schema_tools.py` (module-level builder function)
- `src/mcp_tools_sql/server.py` (register only when `targets.is_multi`)
- Tests: `tests/test_schema_tools.py`, `tests/test_server.py`

## WHAT
A pure-config tool listing the configured targets — **no** database access:
```python
def build_read_databases_tool(targets: ResolvedTargets) -> Callable[..., Awaitable[str]]:
    async def read_databases() -> str: ...
```
Returns a table with columns:
`connection │ database │ backend │ description │ is_default`.
`description` prefers the database description, else the connection description.

## HOW
`server._register_builtin_tools` registers it only when `targets.is_multi`:
```python
if self._targets.is_multi:
    mcp.add_tool(build_read_databases_tool(self._targets),
                 name="read_databases", description=_READ_DATABASES_DESC)
```
Description must state it lists **configured** targets, not a live `sys.databases`
listing (so an allowlist omission is not read as "database does not exist").

## ALGORITHM
```
rows = [{connection: t.connection, database: t.database, backend: t.backend_name,
         description: t.database_description or t.connection_description,
         is_default: t.is_default} for t in targets.targets]
return format_rows(rows, max_rows=len(rows))
```

## DATA
Row dicts as above; formatted via existing `format_rows`.

## TESTS (write first)
- With one target: `read_databases` is **not** registered (server test).
- With multiple targets: registered; output lists every target in config order
  with correct `is_default` and description fallback.
- Tool performs no backend access (pass a registry that raises on `backend_for`;
  calling `read_databases` still succeeds).

## LLM PROMPT
> Implement Step 8 from `pr_info/steps/step_8.md` (context in
> `pr_info/steps/summary.md`). Add `build_read_databases_tool(targets)` to
> `schema_tools.py` returning a config-only async tool that tabulates
> connection/database/backend/description/is_default over `targets.targets`, with
> a description clarifying it lists configured targets (not live `sys.databases`).
> Register it in `server._register_builtin_tools` only when `targets.is_multi`.
> Write tests first (not registered when single; correct rows + is_default when
> multi; no backend access). Run pylint, pytest (`-n auto` + unit markers), mypy,
> lint-imports/tach; all green. One commit.
