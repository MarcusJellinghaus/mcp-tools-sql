# Step 8 — Import contracts: no `mcp` on the export path

## LLM prompt
Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_8.md`.
Run lint-imports, tach, pylint, mypy, pytest (`-n auto`). One commit.

## WHERE
- `.importlinter`
- `tach.toml`

## WHAT
`.importlinter`:
1. Layers contract: insert `mcp_tools_sql.toolset` between `mcp_tools_sql.server` and `mcp_tools_sql.verification`.
2. New contract:
```ini
# Only the MCP server imports the mcp SDK; toolkits, toolset, CLI and
# verification stay importable without it (agent-workbench export path).
[importlinter:contract:no_mcp_on_export_path]
name = No mcp on the export path
type = forbidden
source_modules =
    mcp_tools_sql
forbidden_modules =
    mcp
ignore_imports =
    mcp_tools_sql.server -> mcp
allow_indirect_imports = True
```
(With `include_external_packages = True`, external imports collapse to the top-level `mcp` node, so `mcp.**` would not match, and an unmatched ignore fails the contract.)
3. Add `mcp_tools_sql.toolset` to the `forbidden-imports` contract's `forbidden_modules` for `utils` (consistency with the other tool modules).

`tach.toml`: new module
```toml
[[modules]]
path = "mcp_tools_sql.toolset"
layer = "server"
depends_on = [
    { path = "mcp_tools_sql.schema_tools" }, { path = "mcp_tools_sql.query_tools" },
    { path = "mcp_tools_sql.update_tools" }, { path = "mcp_tools_sql.validation_tools" },
    { path = "mcp_tools_sql.count_tools" }, { path = "mcp_tools_sql.summarize" },
    { path = "mcp_tools_sql.verification" }, { path = "mcp_tools_sql.tool_logging" },
    { path = "mcp_tools_sql.backends" }, { path = "mcp_tools_sql.config" },
    { path = "mcp_tools_sql.utils" },
]
```
`server` module: add `{ path = "mcp_tools_sql.toolset" }`; drop dependencies it no longer imports directly (keep `schema_tools` for the startup counter, `config`, `utils`; remove the others only if tach reports them unused — `exact = false`, so leaving them is harmless).
`cli.commands` keeps depending on `server` only (it reaches the toolset through `server.toolset`).

## Precondition
Steps 4–7 removed every `mcp` import outside `server.py`. If lint-imports still reports a
violation in production code that cannot be removed without changing behaviour, write one line
to `pr_info/.blocked.txt` and stop.

## Tests
No new pytest tests; the checks are lint-imports and tach (both must pass).

## DATA
None.
