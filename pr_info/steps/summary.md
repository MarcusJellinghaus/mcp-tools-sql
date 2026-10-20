# Summary: CLI access to MCP tools (issue #74)

## Goal

Add a `tool` subcommand to the `mcp-tools-sql` CLI that lists, describes, and
invokes every tool the current config would register with the MCP server —
schema introspection, `query_*`, `update_*`, `validate_sql`, `count_records`,
`summarize_columns`, `read_databases` — without an MCP client or LLM.

## Architecture / design changes

**Shared registration, split from transport.** `ToolServer.run()` currently
does two things in one call: register every tool, then start the stdio
transport. It is split into `ToolServer.register_all()` (register only) and
`run()` (`register_all()` + `mcp.run(transport="stdio")`), so the CLI can
build the exact same `FastMCP` instance the server would and inspect its
tools without ever opening stdio. `run_server`'s own wiring (discover config →
load configs → resolve targets → build registry → construct `ToolServer`) is
extracted into `build_tool_server(args) -> tuple[ToolServer, Path]`, reused
by both `run_server` and the new CLI path — this is what guarantees "the
CLI's tool list always matches exactly what the MCP server would register,"
since both paths funnel through one function. `ToolServer` gains two
read-only properties (`config`, `targets`, needed for `run_server`'s existing
log line) and a `close()` method (`self._registry.close_all()`), used by both
`run_server`'s and the CLI's `finally` block.

**New CLI layer: `mcp_tools_sql.cli.commands` → `mcp_tools_sql.server`.**
This is a new dependency edge (the CLI layer did not previously import the
server layer). `tach.toml`'s `mcp_tools_sql.cli.commands` module gains
`mcp_tools_sql.server` in `depends_on`. No `.importlinter` change is needed —
its `layers` contract already lists `cli` above `server`, so `cli → server`
is a higher-importing-lower edge, already legal.

**Two-phase argument parsing.** The legal tool names — and each tool's own
flags — aren't known until config loads, so a single static `argparse` tree
(as used for `init`/`verify`) doesn't fit. `main.py`'s top-level parser gets
a bare `tool` subparser (`add_help=False`, no arguments of its own) and
switches its own top-level call from `parse_args` to `parse_known_args`,
manually replicating `parse_args`'s own "unrecognized arguments" tail check
(verified against CPython's `argparse` source) for every command except
`tool`. Everything `argparse` doesn't recognize after the `tool` token comes
back as `extras`, stored as `args.tool_argv` and handed to
`mcp_tools_sql.cli.commands.tool.run(args)`, which does its own two-level
parsing: first an inner parser with `choices=<tool names>` (unknown name →
exit 2 automatically) and `nargs=argparse.REMAINDER` for the rest, then — for
an actual invocation — a parser built per-tool at runtime from that tool's
own `inspect.Signature`.

(`argparse.REMAINDER` was tried directly on the top-level `tool` subparser
first and rejected: it mishandles a token starting with `-` as the very
first remainder element — e.g. `tool --help` — a known, verified `argparse`
quirk, not a design choice.)

**Dispatch mechanism.** `FastMCP.call_tool()` wraps every exception the tool
body raises into a generic `ToolError`, destroying the type information the
exit-code mapping needs. A fully bare call to `tool.fn(**kwargs)` would skip
pydantic's own coercion and `Field` constraints (e.g. `max_rows`'s floor),
accepting calls the MCP server itself would reject. The CLI instead calls
`tool.fn_metadata.call_fn_with_arg_validation(tool.fn, tool.is_async, kwargs,
None)` directly — the exact step `Tool.run()` uses internally, before it
wraps the result in `ToolError` — so argument validation is identical to the
MCP path and the tool body's real exception type survives.

**Exit-code classification (exit 1 vs. exit 4).** `query_*`, `update_*`, and
the schema builtins don't catch their own exceptions (unlike `validate_sql`/
`count_records`/`summarize_columns`, which always return text and always
exit 0). A raised exception is classified by type, reusing the exact
vocabulary this codebase already established in those three tools' own
`except` chain (`RuntimeError` → "Database connection error"), split one
level finer using the DB-API 2.0 exception hierarchy both drivers already
implement:

| Caught | Exit | Why |
|---|---|---|
| `pydantic.ValidationError` | 3 | pydantic `Field` constraint failed (e.g. `max_rows` floor) |
| `RuntimeError`, `sqlite3.OperationalError`, `sqlite3.InterfaceError`, `pyodbc.OperationalError`, `pyodbc.InterfaceError` | 1 | connection-shaped — matches this codebase's existing `RuntimeError` label |
| `KeyError`, `TypeError`, `ValueError` | 3 | matches this codebase's existing "Invalid parameters"/rejected-call label (e.g. `update_tools.py`'s own body-level `ValueError`) |
| anything else | 4 | backend/SQL execution error (default) |

Verified in this environment: `sqlite3.connect()` and a subsequent "no such
table" both raise `sqlite3.OperationalError` — the stdlib does not
distinguish connection failures from execution failures for SQLite. One
accepted, documented limitation: on SQLite only (the secondary/test backend
here), a missing-table or syntax error exits 1 instead of 4. `pyodbc`'s
analogous split (`OperationalError`/`InterfaceError` for connection,
`ProgrammingError`/`IntegrityError`/`DataError`/`NotSupportedError` for
execution — the latter never checked explicitly, since they fall through to
the exit-4 default) is standard, documented DB-API 2.0 behaviour, not
verified here (`pyodbc` is not installed in this dev environment).

**Argument building.** One scalar CLI flag per tool parameter, generated
from `inspect.signature(tool.fn)` (set by `tool_builder.build_tool_fn` for
every tool already). `params: dict[str, Any] | None` and
`columns: list[str] | None` get repeatable flags instead (`--param
KEY=VALUE`, `--column NAME`); bind values are passed through as strings,
matching the issue's "no JSON, no inference" decision. Every flag uses
`default=argparse.SUPPRESS`, required or not — so an omitted optional flag
is simply absent from the built kwargs dict, which is exactly what
`update_*`'s `_UNSET` sentinel needs ("field omitted" vs. "field explicitly
`None`"). The CLI code never needs to import or reason about `_UNSET`
itself. `required=True` is set only for parameters with no default in the
tool's signature, so a missing required flag is an ordinary `argparse` usage
error (exit 2) — pydantic's own `Field` constraints (exit 3) are reserved for
things `argparse` can't express (e.g. `ge=1`).

## Exit codes (final, documented once in `tool --help`)

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Config/connection error (bad config, can't reach DB — including a connection failure discovered lazily mid-call) |
| 2 | Argparse parse error (unknown flag, unknown tool name, missing required flag) |
| 3 | Tool rejected the call (pydantic `Field` validation, or a body-level `KeyError`/`TypeError`/`ValueError`) |
| 4 | Backend/SQL execution error (query ran, database returned an error) |

`validate_sql`, `count_records`, `summarize_columns` never raise — the CLI
always exits 0 for these three and prints their returned text as-is, no
pattern-matching.

## Files created

- `src/mcp_tools_sql/cli/commands/tool.py` — the `tool` subcommand: config
  loading, bare/`--help` overview, per-tool `--help` detail, unknown-name
  handling, final invocation wiring.
- `src/mcp_tools_sql/cli/commands/tool_help.py` — `render_overview`,
  `render_tool_detail`, the exit-code help text.
- `src/mcp_tools_sql/cli/commands/tool_args.py` — `build_tool_argparser`,
  `build_kwargs`.
- `src/mcp_tools_sql/cli/commands/tool_dispatch.py` — exit-code constants,
  `classify_exception`, `invoke_tool`.
- `tests/cli/test_tool.py`, `tests/cli/test_tool_args.py`,
  `tests/cli/test_tool_dispatch.py`.

## Files modified

- `src/mcp_tools_sql/server.py` — `ToolServer.register_all()`, `config`/
  `targets` properties, `close()`; `build_tool_server(args)` factory;
  `run_server` updated to use it.
- `src/mcp_tools_sql/main.py` — `tool` subparser registration;
  `parse_known_args` + manual "unrecognized arguments" tail check; dispatch
  to `tool.run(args)`.
- `tach.toml` — `mcp_tools_sql.cli.commands` gains `mcp_tools_sql.server` in
  `depends_on`.
- `tests/test_server.py`, `tests/cli/test_main_dispatch.py` — new coverage
  for the above.
- `docs/cli.md` — new `### tool` section (synopsis, exit codes, examples).
- `docs/architecture/architecture.md` — CLI layer section updated to
  describe the shared registration path and the new `cli → server` edge.

## Steps

1. `server.py`: `register_all()` / `build_tool_server()` / `close()`.
2. `tool` subcommand skeleton: discovery surface (list, per-tool detail,
   unknown-name handling), wired into `main.py`.
3. `tool_args.py`: dynamic per-tool argument parser + kwargs builder
   (standalone, unit-tested).
4. `tool_dispatch.py`: exit-code classifier + `invoke_tool`
   (standalone, unit-tested).
5. Wire steps 3 and 4 into `tool.py`'s dispatch: full end-to-end invocation.
6. Docs: `docs/cli.md` and `docs/architecture/architecture.md`.

Each step is one commit: tests + implementation + `run_pylint_check` /
`run_pytest_check` / `run_mypy_check` / `run_ruff_check` /
`run_lint_imports_check` / `run_tach_check` passing, `run_format_code` run
before committing.
