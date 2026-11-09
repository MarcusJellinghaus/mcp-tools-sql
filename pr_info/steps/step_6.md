# Step 6 — `ToolServer(toolset)` and eager `build_tool_server`

## LLM prompt
Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_6.md`.
Rewrite the affected tests first, then `server.py`. Run pylint, mypy, vulture, pytest (`-n auto`). One commit.

## WHERE
- `src/mcp_tools_sql/server.py`
- `src/mcp_tools_sql/cli/commands/tool.py` — minimal: drop the `server.register_all()` call (full rework in step 7)
- `vulture_whitelist.py` — remove `_.create_server`
- Tests: `tests/test_server.py`, `tests/test_server_verify_tool.py`, `tests/test_query_limits_tools.py`

## WHAT
```python
class ToolServer:
    def __init__(self, toolset: SqlToolset) -> None   # FastMCP + register every spec via FastMCPSink
    @property mcp -> FastMCP
    @property toolset -> SqlToolset
    def run(self) -> None                             # self._mcp.run(transport="stdio") only
    def close(self) -> None                           # self._toolset.close()

def build_tool_server(args: argparse.Namespace) -> tuple[ToolServer, Path]
def run_server(args: argparse.Namespace) -> None
```
Remove: `register_all`, `_register_builtin_tools`, `_register_configured_tools`, `_build_verify_tool`,
`config`/`targets` properties, `create_server`, `_READ_DATABASES_DESC`, `_VERIFY_DESC`, `_RESTART_NOTE`
and the toolkit/verification imports no longer used.

## ALGORITHM
```
ToolServer.__init__(toolset):
  self._toolset = toolset; self._mcp = FastMCP("mcp-tools-sql")
  sink = FastMCPSink(self._mcp)
  for spec in toolset.specs: sink.add(spec)

build_tool_server(args):
  qpath = discover_query_config(args.config, project_dir=Path.cwd())
  toolset = build_toolset(qpath, args.database_config)
  return ToolServer(toolset), qpath
```
`run_server`: unchanged structure (`try: log; server.run() finally: server.close()`), log reads
`server.toolset.targets` and `server.toolset.query_config.connection`.

## HOW
- `server.py` imports `build_toolset`, `SqlToolset` from `mcp_tools_sql.toolset`; keeps `load_default_queries`, `PROGRAMMATIC_BUILTIN_TOOLS` for the startup counter.
- `cli/commands/tool.py`: delete `server.register_all()` so it keeps working until step 7.

## Tests
- Replace `ToolServer(qcfg, targets, registry, allow_updates=X)` + `_register_*()` / `register_all()` with
  `ToolServer(assemble_toolset(qcfg, targets, registry, X))`; close via `server.close()`.
  Tests that registered only configured tools (e.g. write-query gate, update tool) still assert on names — the extra builtins don't matter.
- `test_build_tool_server_returns_unregistered_server` → `test_build_tool_server_registers_tools`: tools are present right after `build_tool_server`; `qpath == args.config`.
- `test_register_all_registers_builtin_and_configured_tools` → constructor registers both.
- `test_run_server_reads_allow_updates_from_database_config` → patch `mcp_tools_sql.toolset.assemble_toolset` (as referenced from `toolset.build_toolset`) with a recording wrapper; assert `allow_updates is False`.
- `test_close_delegates_to_registry_close_all`: `server.close()` → `close_all` called once. Add: `run_server` closes exactly once (patch `run` to no-op, count `close_all`).
- `test_config_and_targets_properties_expose_constructor_values` → `server.toolset is toolset`.
- New: `build_tool_server` with a query pinned to an unknown connection raises `ValueError` (eager build).
- New parity test: for a config with a query, an update (`allow_updates=true`) and multi-target, MCP `list_tools()` names/descriptions equal the specs', and each tool's `inputSchema["properties"][p].get("description")` equals `spec.args_model.model_json_schema()["properties"][p].get("description")` (suppress `PydanticJsonSchemaWarning`).
- `tests/test_server_verify_tool.py`: drop `register_all()` calls; `_RESTART_FRAGMENT` → `"the running tools keep the config they were built with"`; `test_verify_registered_without_path_kwargs` uses `ToolServer(assemble_toolset(...))`.
- `tests/test_query_limits_tools.py:~424`: same replacement.

## DATA
`build_tool_server` → `(ToolServer, Path)` as before, now fully registered.
