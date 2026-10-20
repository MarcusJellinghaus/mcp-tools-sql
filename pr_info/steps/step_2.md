# Step 2: `tool` subcommand skeleton — discovery surface

Read `pr_info/steps/summary.md` first. This step makes
`mcp-tools-sql tool`, `mcp-tools-sql tool --help`, and
`mcp-tools-sql tool <name> --help` work end-to-end, including a bad-config
error path and an unknown tool name. It does **not** yet invoke a tool
(that's steps 3-5).

**Precondition:** Step 1 is merged — `server.py` exposes `build_tool_server`,
`ToolServer.register_all()`, `ToolServer.close()`. If it does not, write one
line to `pr_info/.blocked.txt` and stop.

## WHERE

- `src/mcp_tools_sql/main.py` (modified)
- `src/mcp_tools_sql/cli/commands/tool.py` (new)
- `src/mcp_tools_sql/cli/commands/tool_help.py` (new)
- `tach.toml` (modified)
- `tests/cli/test_tool.py` (new)
- `tests/cli/test_main_dispatch.py` (modified — new dispatch tests only)

## WHAT

`tool_help.py`:

```python
EXIT_CODE_HELP: str   # the 0-4 table from summary.md, as a plain-text block

def render_overview(tools: Sequence[Tool]) -> str: ...
def render_tool_detail(tool: Tool) -> str: ...
```

`tool.py`:

```python
def add_subparser(subparsers: argparse._SubParsersAction) -> None: ...
def run(args: argparse.Namespace) -> int: ...
```

`main.py` changes: register the `tool` subparser, switch the top-level
parse call to `parse_known_args`, dispatch `command == "tool"` to
`tool.run(args)`.

## HOW

- `tool_help.render_overview` sorts tools by name, one line per tool:
  `name` padded, then the first non-blank line of `tool.description`
  (`Tool.description` is `FastMCP`'s copy of the registered docstring —
  already set by `build_tool_fn`/`mcp.add_tool(..., description=...)` for
  every tool in this codebase). Appends `EXIT_CODE_HELP` after a blank line.
- `tool_help.render_tool_detail` reads `tool.description` (full text) and
  `tool.parameters` (the JSON schema `Tool.from_function` already built from
  the tool's `inspect.Signature` and `Field` metadata) — iterates
  `properties`, marks each `required` per the schema's `required` list,
  and prints `type`/`enum` (choices)/`default`/`description` per parameter.
  Does **not** include `EXIT_CODE_HELP` (documented once, in the overview,
  per the issue).
- `tool.py: run(args)`:
  1. Call `build_tool_server(args)` (from `mcp_tools_sql.server`); on
     `ValueError`/`OSError`, print `f"Error: {exc}"` to stderr, return 1 —
     same convention as `init`/`verify`.
  2. `server.register_all()`; always `server.close()` in `finally` (no live
     connection is opened by registration itself — `BackendRegistry.backend_for`
     is lazy — but `close()` is a no-op-safe habit matching `run_server`).
  3. Read `args.tool_argv: list[str]` (set by `main.py`, see below).
  4. If `not tool_argv or tool_argv[0] in ("--help", "-h")`: print
     `render_overview(mcp._tool_manager.list_tools())`, return 0.
  5. Otherwise build an inner parser: positional `name` with
     `nargs="?"`, `default=None`, `choices=sorted(tool_names)`, plus
     `rest` with `nargs=argparse.REMAINDER` (REMAINDER is safe here —
     unlike step 2's rejected top-level use, `name` has already consumed
     the first token, so `rest`'s first element is never the very first
     token of the whole list). Use `cli.parsers.HelpHintArgumentParser`
     so an unknown name exits 2 with the existing usage-hint convention.
  6. If `not ns.rest or ns.rest[0] in ("--help", "-h")`: print
     `render_tool_detail(tool)`, return 0.
  7. Otherwise: this is where step 5 wires in the actual invocation. For
     this step, raise `NotImplementedError` — unreachable in this step's
     own tests, since no test yet passes real tool arguments past a name.
- `main.py`:
  - `tool.add_subparser(subparsers)` registers `subparsers.add_parser("tool",
    add_help=False, help="List and call MCP tools directly (bypasses the MCP
    client).")` — no arguments of its own.
  - `main()` changes `args = parser.parse_args(argv)` to
    `args, extras = parser.parse_known_args(argv)`, then:
    `if (args.command or "server") != "tool" and extras: parser.error("unrecognized arguments: " + " ".join(extras))`
    — this is `argparse.ArgumentParser.parse_args`'s own tail check,
    inlined, so every command except `tool` is exactly as strict as before.
  - Dispatch: `if command == "tool": args.tool_argv = extras; return
    tool.run(args)`.
- `tach.toml`: add `{ path = "mcp_tools_sql.server" }` to the `depends_on`
  list of the `mcp_tools_sql.cli.commands` module entry.

## ALGORITHM

```
tool.run(args):
    try:
        server, _qpath = build_tool_server(args)
    except (ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    try:
        server.register_all()
        tools = server.mcp._tool_manager.list_tools()
        tool_argv = args.tool_argv
        if not tool_argv or tool_argv[0] in ("--help", "-h"):
            print(render_overview(tools)); return 0
        name_parser = build_name_parser([t.name for t in tools])
        ns = name_parser.parse_args(tool_argv)   # unknown name -> SystemExit(2)
        tool = server.mcp._tool_manager.get_tool(ns.name)
        if not ns.rest or ns.rest[0] in ("--help", "-h"):
            print(render_tool_detail(tool)); return 0
        raise NotImplementedError  # wired in step 5
    finally:
        server.close()
```

## DATA

No new persistent data structures; `render_overview`/`render_tool_detail`
return plain strings printed as-is.

## Tests (write first)

`tests/cli/test_tool.py` (new; build a small sqlite `mcp-tools-sql.toml`/
`db.toml` pair per test, following the pattern in `tests/test_server.py`'s
`_write_sqlite_configs`):

1. Bare `tool` and `tool --help` both print the full overview (same
   output), including the exit-code table, and return 0.
2. The overview includes a builtin (`read_tables`) and a configured
   `query_*` tool; excludes `update_*` tools when the database config sets
   `allow_updates = false`, includes them when `true`.
3. `tool some_registered_name --help` prints a detail block containing the
   tool's full docstring and every parameter name.
4. `tool bogus_name` exits 2 and prints a usage hint to stderr (no
   traceback).
5. A missing `--config` path (nonexistent file) makes bare `tool` print a
   clean one-line error and exit 1 — no traceback.

`tests/cli/test_main_dispatch.py`: add a test that `main(["tool"])`
dispatches to `tool.run` (monkeypatched, mirroring the existing
`test_dispatch_init_calls_init_run` pattern) and one confirming
`main(["init", "--backend", "bogus"])` still exits 2 (regression check that
the new `parse_known_args` tail-check doesn't loosen non-`tool` commands).

## Commit

One commit: the tests above, `tool.py`/`tool_help.py`, the `main.py` and
`tach.toml` changes, all checks passing.

## LLM prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_2.md`. Implement
> step 2 exactly as specified: the `tool` subcommand's discovery surface
> (overview listing, per-tool `--help` detail, unknown-name handling,
> config-error handling), wired into `main.py` via `parse_known_args` as
> described. Write the tests in `tests/cli/test_tool.py` and the new
> `test_main_dispatch.py` cases first, then the implementation. The final
> invocation branch (anything past `tool <name> --help`) should raise
> `NotImplementedError` for now — later steps wire it in. Update `tach.toml`
> for the new `cli.commands -> server` dependency. Run pylint, pytest, mypy,
> ruff, lint-imports, and tach checks before committing.
