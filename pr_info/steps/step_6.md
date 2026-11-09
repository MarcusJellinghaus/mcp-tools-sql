# Step 6 — MCP tool `verify`

## LLM prompt

> Read `pr_info/steps/summary.md` (section 6), then implement **this step only**
> (`pr_info/steps/step_6.md`). Do TDD: write `tests/test_server_verify_tool.py` first, then
> implement. Existing positional `ToolServer(qcfg, targets, registry, allow_updates=...)`
> calls in tests must keep working unchanged. Run pylint, pytest (`-n auto`), mypy, ruff,
> lint-imports, tach and format_code, then make one commit.

## WHERE

- `src/mcp_tools_sql/server.py`
- `src/mcp_tools_sql/schema_tools.py`
- `tach.toml`
- `tests/test_server_verify_tool.py` (**new**)
- any test asserting the exact built-in tool set (grep `tests/` for `list_tools` set
  equality and `render_overview` expectations)
- `docs/cli.md`, `docs/architecture/architecture.md`

## WHAT

```python
# schema_tools.py
PROGRAMMATIC_BUILTIN_TOOLS = ("validate_sql", "count_records", "summarize_columns", "verify")

# server.py
_VERIFY_DESC = (
    "Re-run the `mcp-tools-sql verify` checks against the config files on disk: config "
    "parse, dependencies, connectivity of every configured connection, EXPLAIN of every "
    "configured query, update tables/columns. Returns a short summary plus every failing "
    "or warning row. Use it after a query fails to check config and connectivity. Takes "
    "a few seconds."
)
_RESTART_NOTE = (
    "Note: verify re-read the config files from disk; this server keeps using the config "
    "it loaded at startup. Config edits need a server restart to take effect."
)

class ToolServer:
    def __init__(self, config, targets, registry, allow_updates, *,
                 query_config_path: Path | None = None,
                 database_config_path: Path | None = None) -> None
    def _build_verify_tool(self) -> Callable[[], Awaitable[str]]

def create_server(config, targets, registry, allow_updates, *,
                  query_config_path: Path | None = None,
                  database_config_path: Path | None = None) -> ToolServer
```

## HOW

- `server.py` imports `verify_all` from `mcp_tools_sql.verification`, `render_short` from
  `mcp_tools_sql.verification.render`, and `log_tool_call` from
  `mcp_tools_sql.tool_logging`.
- `_register_builtin_tools`: after the existing registrations, add
  `self._mcp.add_tool(self._build_verify_tool(), name="verify", description=_VERIFY_DESC)`.
- `build_tool_server` constructs
  `ToolServer(qcfg, targets, registry, dbcfg.security.allow_updates, query_config_path=qpath, database_config_path=args.database_config)`.
  `create_server` forwards both kwargs.
- `tach.toml`, module `mcp_tools_sql.server`: add `{ path = "mcp_tools_sql.verification" }`
  and `{ path = "mcp_tools_sql.tool_logging" }` to `depends_on`.
- The tool never uses `self._registry`; `verify_all` creates and closes its own.

## ALGORITHM

```
def _build_verify_tool(self):
    qpath, dbpath = self._query_config_path, self._database_config_path
    async def verify() -> str:
        async with log_tool_call("verify"):
            result = verify_all(qpath, dbpath)   # None paths -> discovery from cwd / default db path
        return f"{render_short(result)}\n\n{_RESTART_NOTE}"
    return verify
```

## DATA

The tool returns a `str`: the `render_short` output, a blank line, then `_RESTART_NOTE`.

## Precondition

If FastMCP rejects registering a zero-argument async tool, write one line to
`pr_info/.blocked.txt` and stop. `read_databases` already uses this pattern.

## Tests (write first): `tests/test_server_verify_tool.py`

Build valid sqlite configs in `tmp_path`, create the server with
`build_tool_server(argparse.Namespace(config=q, database_config=db))`, call
`register_all()`, and use `create_connected_server_and_client_session` (as in
`tests/test_server.py`):

- `verify` is in `list_tools()`.
- `call_tool("verify", {})` text starts with `Config loaded.` and contains
  `Config edits need a server restart`.
- The tool re-reads the database config from disk and never shows credentials: after
  building the server, overwrite the database config file with an mssql connection whose
  `database`/`databases` conflict and whose `password = "s3cret-pw"`. The output contains
  `Config has errors.`, does not contain `s3cret-pw`, and still has the restart note.
- No built-in tool name starts with `query_` or `update_`: a server with no configured
  queries or updates, after `register_all()`, lists no tool name with either prefix.
- `ToolServer(qcfg, targets, registry, allow_updates=False)` with no path kwargs still
  registers `verify`.
- After `call_tool("verify")`, the server's registry is untouched: a configured query tool
  still works afterwards.
- Update any test that asserts the exact built-in tool set. The `builtin_tools=N` counter
  test derives from `PROGRAMMATIC_BUILTIN_TOOLS` and needs no change.

## Docs

- `docs/cli.md`: add `verify` to the tool list in the `tool` section.
- `docs/cli.md`, `verify` section: one paragraph on the MCP `verify` tool:
  - it returns the short summary;
  - it re-reads files from disk, and edits need a restart;
  - it cannot diagnose a config that prevents startup; use the CLI for that.
- `architecture.md`:
  - `verification/` is consumed by the server's `verify` tool;
  - the server → verification dependency;
  - replace the "planned: MCP-server health endpoint" wording.
