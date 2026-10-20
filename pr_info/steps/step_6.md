# Step 6: documentation

Read `pr_info/steps/summary.md` first. Documentation only — no code or test
changes. TDD does not apply to this step.

**Precondition:** Step 5 is merged (the `tool` subcommand is fully
functional). If it is not, write one line to `pr_info/.blocked.txt` and
stop.

## WHERE

- `docs/cli.md` (modified)
- `docs/architecture/architecture.md` (modified)

## WHAT

No functions — prose and examples only.

## HOW

`docs/cli.md`: add a `### tool` section after the existing `### verify`
section, following the file's existing style (synopsis block, flags table,
examples, matching the level of detail already given to `init`/`verify`).
Cover:

- Synopsis: `mcp-tools-sql tool`, `mcp-tools-sql tool --help`,
  `mcp-tools-sql tool <name> --help`, `mcp-tools-sql tool <name> --flag
  value ...`.
- That bare `tool` and `tool --help` are the same code path (no `--list`
  flag).
- The repeatable `--param KEY=VALUE` / `--column NAME` convention for
  `validate_sql`/`count_records`/`summarize_columns`, and that `params`
  values are passed through as plain strings.
- The `update_*` omitted-vs-explicit-`None` field behaviour (a flag not
  passed leaves the column unchanged; nothing in this CLI can "pass an
  explicit `None`" for an optional field — only omission is possible with a
  scalar flag, so document that passing the flag always sets a value).
- The exit codes table from `summary.md`, verbatim.
- Two or three short worked examples (one schema/query call, one `update_*`
  call, one `validate_sql --param` call) mirroring the existing `init`/
  `verify` examples' style (`$ mcp-tools-sql ...` / expected output block).

`docs/architecture/architecture.md`: in the existing "CLI Layer
(`mcp_tools_sql.cli`)" subsection, add 2-3 sentences describing: the new
`cli.commands -> server` dependency (`build_tool_server`/
`register_all()`/`close()` shared with `run_server`, guaranteeing the CLI's
tool list matches the MCP server's); and the two-phase argument parsing
(`parse_known_args` at the top level, a per-tool `argparse.ArgumentParser`
built at runtime from each tool's `inspect.Signature`).

## ALGORITHM

Not applicable (documentation only).

## DATA

Not applicable.

## Commit

One commit: the two doc files, `run_format_code` not needed (docs only),
but still run `run_pylint_check` / `run_pytest_check` / `run_mypy_check` /
`run_ruff_check` to confirm the doc-only change didn't break anything.

## LLM prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_6.md`. Update
> `docs/cli.md` with a new `### tool` section and
> `docs/architecture/architecture.md`'s CLI Layer subsection, exactly as
> specified. No code or test changes. Run pylint, pytest, mypy, and ruff
> checks before committing (sanity check only — this step is docs-only).
