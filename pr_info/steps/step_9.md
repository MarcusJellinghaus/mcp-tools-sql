# Step 9 — Docs

## LLM prompt
Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_9.md`.
Docs only. Run pytest (`-n auto`) to confirm nothing depends on the old text. One commit.

## WHERE / WHAT
- `docs/cli.md` (the `verify` tool paragraph, ~line 224): replace "while the server keeps the config it loaded at startup: config edits need a server restart to take effect" with: the running tools keep the config they were built with; an MCP server picks up edits on restart, agent-workbench on Reload. Keep the "A config that stops the server from starting…" sentence.
- `docs/architecture/architecture.md`:
  - Layer diagram: add a `Toolset Layer` box (`mcp_tools_sql.toolset`) between Server and Tool layers; mention `count_tools`, `summarize` in the Tool layer if missing.
  - `tool` subcommand paragraph: `build_tool_server()` builds the toolset eagerly and returns a fully registered `ToolServer`; the CLI lists and calls `server.toolset.specs` (validation via `args_model`), so its tool list matches the MCP server's.
  - `verify` paragraph: `toolset` (not `server`) depends on `verification`; the tool returns `render_short` output plus a note that the running tools keep the config they were built with.
  - New short "Toolset (`mcp_tools_sql.toolset`)" subsection: `build_toolset(query_config, database_config=None) -> SqlToolset`; `assemble_toolset` from loaded objects; `.specs`/`.targets`/`.query_config`/`.close()`/context manager; groups and `read_only` table; rebuild = build again and close the old one; no `mcp` import (contract).
  - Key modules table: add `toolset.py`; `server.py` → "Registers the toolset's specs into FastMCP, starts STDIO transport"; `verification/` row: "the toolset's `verify` tool".
- `docs/quality-and-security-checks.md` (isolation contract list, ~line 89): add
  "- `no_mcp_on_export_path` forbids importing `mcp` anywhere except `mcp_tools_sql.server`, so the toolset can be used without the MCP SDK."

## Tests
None new.
