# Summary — Export tools as ToolSpecs from one factory (#96)

Part of agent-workbench#13 (step 2a). Builds on mcp-coder-utils#57 (`tool_spec` contract).

## Goal

One tool list for every consumer. The MCP server, the CLI `tool` subcommand and
agent-workbench get the same tools (names, descriptions, validation, groups) from
one factory, as `ToolSpec`s, without importing `mcp`:

```
build_toolset(query_config, database_config) -> SqlToolset (.specs, .close())
   ├─ MCP server:      ToolServer(toolset) registers specs into FastMCP
   ├─ CLI `tool`:      lists and calls server.toolset.specs
   └─ agent-workbench: wraps the specs as LangChain tools
```

## Architectural / design changes

| Area | Before | After |
|---|---|---|
| Toolkit API | `register(mcp: FastMCP)` calls `mcp.add_tool` | `register(sink: ToolSink)` adds `tool_spec(...)` results; no `mcp` import in any toolkit |
| Tool assembly | `ToolServer._register_builtin_tools/_register_configured_tools/register_all` | `mcp_tools_sql.toolset.assemble_toolset(...)` collects every spec into a `ToolCollector` |
| Built-ins `verify`, `read_databases` | Registered by `ToolServer` | Built by the toolset, so every consumer gets them |
| Server | `ToolServer(config, targets, registry, allow_updates, ...)`, lazy `register_all()` in `run()` | `ToolServer(toolset)` registers all specs in its constructor via `FastMCPSink`; `run()` only runs; `close()` → `toolset.close()` |
| `build_tool_server(args)` | Builds an unregistered server | Discovers the query config, builds the toolset eagerly, returns a fully registered server |
| CLI `tool` | Reads FastMCP's private `_tool_manager` | Uses `ToolSpec`s: schema from `args_model`, dispatch via `args_model.model_validate` |
| Empty descriptions | Passed through to FastMCP | Toolkits generate a fallback; `verify` reports a `<name>.description` WARN row |
| Missing optional kwargs | Only FastMCP's "pass every field" convention worked | `build_tool_fn` applies signature defaults, so callers passing only present keys (LangChain) work |
| Import contracts | — | New forbidden contract: nothing in `mcp_tools_sql` imports `mcp` except `server`; `toolset` layer between `server` and `verification` |
| `verify` note | "Config edits need a server restart" | Neutral: valid for MCP restart and agent-workbench Reload |
| Dead code | `create_server` | Removed |

Layers (top → bottom): `main` → `cli` → `server` → **`toolset`** → `verification` →
tool modules → `query_helpers` → `tool_builder` → … → `utils`.

### Groups and `read_only`

| Group | Tools | read_only |
|---|---|---|
| `sql.schema` | tools from `default_queries.toml`, `read_databases` | True |
| `sql.validation` | `validate_sql`, `verify` | True |
| `sql.profiling` | `count_records`, `summarize_columns` | True |
| `sql.query` | `query_*` | True |
| `sql.update` | `update_*` | False |

Group names are plain string literals at each `tool_spec(...)` call (KISS — no constants module).

### Key design decisions (KISS)

- No rebuild method: `build_toolset(...)` is callable repeatedly; the consumer swaps and closes the old one.
- `assemble_toolset` (lower-level builder from loaded objects) owns the registry once called and closes it if the build fails; `build_toolset(paths)` loads the files and delegates.
- `FastMCPSink` lives in `server.py`; toolkit tests call `.register(FastMCPSink(mcp))` directly (no extra test helper).
- `ToolServer` exposes `.mcp` and `.toolset`; the old `.config` / `.targets` properties are removed (`server.toolset.query_config`, `server.toolset.targets`).
- CLI keeps calling `build_tool_server(args)` (cwd discovery, config-error hint) and uses `server.toolset.specs`.
- Duplicate tool names now raise (`ToolCollector`); none are possible today.

## Files created / modified

### Created
- `src/mcp_tools_sql/utils/tool_spec.py` — shim re-exporting `ToolSpec`, `tool_spec`, `ToolSink`, `ToolCollector`
- `src/mcp_tools_sql/toolset.py` — `SqlToolset`, `assemble_toolset`, `build_toolset`, `verify` tool
- `tests/test_tool_spec_shim.py`
- `tests/test_toolset.py`

### Modified (source)
- `src/mcp_tools_sql/tool_builder.py` — apply signature defaults
- `src/mcp_tools_sql/schema_tools.py`, `query_tools.py`, `update_tools.py`, `validation_tools.py`, `count_tools.py`, `summarize/tools.py` — `register(sink)`
- `src/mcp_tools_sql/server.py` — `FastMCPSink`, `ToolServer(toolset)`, eager `build_tool_server`, remove `create_server`
- `src/mcp_tools_sql/verification/queries.py`, `verification/updates.py` — description WARN row
- `src/mcp_tools_sql/cli/commands/tool.py`, `tool_args.py`, `tool_dispatch.py`, `tool_help.py` — specs instead of FastMCP `Tool`
- `vulture_whitelist.py` — drop `_.create_server`
- `.importlinter`, `tach.toml`
- `pyproject.toml` — `mcp-coder-utils` pin bump (last step)
- `.claude/CLAUDE.md` — Shared Libraries list
- `docs/cli.md`, `docs/architecture/architecture.md`, `docs/quality-and-security-checks.md`

### Modified (tests)
- Toolkit tests: `tests/test_count_tools.py`, `test_query_tools.py`, `test_query_tools_readonly.py`, `test_query_limits_tools.py`, `test_schema_tools.py`, `test_schema_tools_multitarget.py`, `test_tool_timeouts.py`, `test_update_tools.py`, `test_update_tools_multitarget.py`, `test_validation_tools.py`, `test_validation_tools_multitarget.py`, `tests/summarize/test_tools.py`, `tests/summarize/tool_helpers.py`
- `tests/test_tool_builder.py`
- `tests/test_server.py`, `tests/test_server_verify_tool.py`
- `tests/cli/test_tool_args.py`, `tests/cli/test_tool_dispatch.py`, `tests/cli/test_tool.py` (if needed)
- `tests/verification/test_queries.py`, `tests/verification/test_updates.py` (if row keys asserted), `tests/cli/fixtures/verify_snapshot.txt`, `tests/cli/test_verify_output.py`
- `tests/test_module_imports.py` — `mcp` not in `sys.modules` check

## Steps

1. `utils/tool_spec.py` shim
2. `build_tool_fn` applies signature defaults
3. `verify` description WARN row
4. Toolkits register into a `ToolSink` (+ `FastMCPSink`, fallback descriptions)
5. `toolset` module
6. `ToolServer(toolset)` and eager `build_tool_server`
7. CLI `tool` subcommand on specs
8. Import contracts (import-linter, tach)
9. Docs
10. `mcp-coder-utils` pin bump
