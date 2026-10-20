# Step 5: wire argument parsing and dispatch into `tool.py` — full invocation

Read `pr_info/steps/summary.md` first. This step replaces step 2's
`raise NotImplementedError` placeholder with the real invocation path,
completing `mcp-tools-sql tool <name> --arg value ...` end-to-end.

**Precondition:** Steps 2, 3, and 4 are merged —
`src/mcp_tools_sql/cli/commands/tool.py` has the `NotImplementedError`
placeholder from step 2, and `tool_args.py` / `tool_dispatch.py` exist with
the functions described in steps 3-4. If any of these does not hold, write
one line to `pr_info/.blocked.txt` and stop.

## WHERE

- `src/mcp_tools_sql/cli/commands/tool.py` (modified — replace the
  placeholder branch only)
- `tests/cli/test_tool.py` (modified — new end-to-end tests appended)

## WHAT

No new public functions. `tool.run`'s final branch (step 2's
`raise NotImplementedError`) becomes:

```python
parser = build_tool_argparser(tool, prog=f"mcp-tools-sql tool {ns.name}")
tool_ns = parser.parse_args(ns.rest)        # argparse errors -> SystemExit(2), unchanged
kwargs = build_kwargs(tool_ns)
exit_code, output = asyncio.run(invoke_tool(tool, kwargs))
print(output)
return exit_code
```

## HOW

- Import `build_tool_argparser`, `build_kwargs` from `.tool_args` and
  `invoke_tool` from `.tool_dispatch` at the top of `tool.py`.
- `parser.parse_args(ns.rest)` (not `parse_known_args`) — a genuinely bad
  per-tool flag is an ordinary `argparse` usage error here, exit 2,
  propagating via the normal uncaught-`SystemExit` path `main.py` already
  relies on for every other subcommand.
- Nothing else in `tool.py` changes — the overview/detail/unknown-name
  branches from step 2 are untouched.

## ALGORITHM

(Only the new tail of `tool.run`'s per-tool branch — the rest is unchanged
from step 2's `ALGORITHM` block.)

```
... (name resolved, ns.rest is non-empty and not --help/-h) ...
parser = build_tool_argparser(tool, prog=f"mcp-tools-sql tool {ns.name}")
tool_ns = parser.parse_args(ns.rest)
kwargs = build_kwargs(tool_ns)
exit_code, output = asyncio.run(invoke_tool(tool, kwargs))
print(output)
return exit_code
```

## DATA

No new data structures.

## Tests (write first)

Append to `tests/cli/test_tool.py`, each using a small sqlite fixture db
(reuse `tests/conftest.py`'s `sqlite_db` or build one inline per the
`_write_sqlite_configs` pattern in `tests/test_server.py`):

1. `tool read_tables` (a builtin schema tool) against a seeded sqlite db →
   exit 0, output contains the seeded table name(s).
2. A configured `[queries.foo]` entry → `tool query_foo --id 1` → exit 0,
   output contains the expected row.
3. `tool query_foo --max_rows -5` (a deliberately invalid value for a
   `Field(ge=MAX_ROWS_MIN)`-constrained param) → exit 3, no traceback.
4. `tool query_bad_table` configured against a SQL referencing a
   non-existent table → exit 4, no traceback.
5. A configured `[updates.set_name]` entry with one optional field: call
   `tool update_set_name --id 1 --name Alice` then read the row back and
   confirm `name == "Alice"`; call `tool update_set_name --id 1`
   (optional field omitted) and confirm the column is unchanged (not set to
   `NULL`) — the `_UNSET`-vs-explicit-`None` distinction working end to end.
6. `tool validate_sql --sql "SELECT 1 WHERE :id = :id" --param id=5` → exit
   0, output is `"Valid."`.
7. `tool summarize_columns --schema main --table customers --column id
   --column name` → exit 0, output only profiles the requested columns.
8. A connection failure (point `--database-config` at a sqlite path whose
   parent directory doesn't exist, so `sqlite3.connect` itself fails) on a
   tool that actually touches the DB (e.g. `read_tables`) → exit 1.

## Commit

One commit: the tests above, the `tool.py` change, all checks passing.

## LLM prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_5.md`. Replace the
> `NotImplementedError` placeholder in
> `src/mcp_tools_sql/cli/commands/tool.py` (from step 2) with the real
> invocation path, using `build_tool_argparser`/`build_kwargs` from
> `tool_args.py` (step 3) and `invoke_tool` from `tool_dispatch.py` (step 4).
> Write the end-to-end tests appended to `tests/cli/test_tool.py` first,
> then the implementation. Run pylint, pytest, mypy, ruff, lint-imports, and
> tach checks before committing.
