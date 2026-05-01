# Step 10 — Documentation: fix existing-doc gaps + add CLI reference

**Reference**: [summary.md](./summary.md)
**Commit**: 10 of 10 — final
**Goal**: Update all existing user-facing documentation that references obsolete config fields or names, add a brief note about the new `cli/` layer, clean up the vulture whitelist, and ship a new CLI reference doc covering `init` and `verify`.

This step is intentionally separate from the implementation steps because it touches multiple unrelated docs and the CLI surface only stabilizes after step 9. Couples weakly to every step but coherently to none — a dedicated step keeps the prior commits surgical.

---

## WHERE

Modify:
- `mcp-tools-sql.md` — line ~859, code block still has `connection_string=`; update consistent with step 2's removal (use `path=` for sqlite).
- `README.md` — Quick Start section: verify it matches the actual `init` / `verify` UX delivered by this PR; update if needed (flag names, output snippets, examples).
- `docs/architecture/architecture.md` — add a short note about the new `cli/` layer per the importlinter contract (where it sits between `main` and `server`, what it can/cannot import).
- `vulture_whitelist.py` — remove the `_.connection_string` entry (line ~55) and the `_.load_user_config` entry (line ~85). Both names no longer exist after steps 1–2.

Create:
- `docs/cli.md` — CLI reference doc covering both `init` and `verify` commands, all flags, example output, exit codes.

---

## WHAT — Each file

### `mcp-tools-sql.md` (~line 859)

Find the example block that still uses `connection_string=` and rewrite it to use the new `ConnectionConfig` shape (sqlite → `path=`; mssql → `host`/`port`/`database`/`username`/`credential_env_var`/`driver`). Use grep on `connection_string` across the file; there should be no remaining occurrences after this step.

### `README.md` Quick Start

Walk the Quick Start narrative end-to-end against the actual delivered CLI. Specifically:
- Replace any `--user-config` references with `--database-config`.
- If the section currently shows manual config-file authoring, replace with `mcp-tools-sql init --backend sqlite` (or similar) and a `mcp-tools-sql verify` step.
- If it shows a `connection_string = ...` example, update to `path = "./mydb.db"` for sqlite (or appropriate fields for other backends).
- Confirm the example exit codes / behavior match the implementation.

### `docs/architecture/architecture.md`

Add a short paragraph (or update the existing layer diagram) noting:
- New `mcp_tools_sql.cli` package between `main` and `server` in the layered import contract.
- `cli` may import from `config`, `utils`, `backends`, `schema_tools`, `formatting`. It is the **only** layer between `main` and `server`.
- The `init` and `verify` subcommands live in `cli/commands/`.

### `vulture_whitelist.py`

Remove:
```
_.connection_string
```
on line ~55, and
```
_.load_user_config
```
on line ~85.

Run `mcp__tools-py__run_vulture_check` after the edit to confirm no new dead-code warnings appear.

### `docs/cli.md` (new)

Suggested outline (concise — this is a reference doc, not a tutorial):

```
# mcp-tools-sql CLI Reference

## Synopsis
mcp-tools-sql [--config PATH] [--database-config PATH] [--log-level LEVEL]
              [--log-file PATH] [--console-only] [--version] [--help]
              <command> [<args>]

## Global flags
... table of flags with descriptions, defaults ...

## Commands

### init
mcp-tools-sql init --backend {sqlite|mssql|postgresql}
                   [--output PATH] [--pyproject]
... description, behavior, examples (one per backend), exit codes ...

### verify
mcp-tools-sql verify [--config PATH] [--database-config PATH]
... section-by-section description (ENVIRONMENT, CONFIG, DEPENDENCIES, BUILTIN,
    CONNECTION, INSTALL INSTRUCTIONS, QUERIES, UPDATES) ...
... example output for the SQLite happy path ...
... exit codes (0 / 1) ...

### help / --version
... brief notes ...

## Exit codes
0  success
1  user-recoverable error (missing config, failed connection, ...)
2  argparse parse error
```

Cross-link from `README.md` Quick Start.

---

## HOW — Integration points

- This step has **no source-code edits** — purely docs + whitelist cleanup. Quality gates remain green if previous steps were correct.
- Docs use the same TOML / shell snippets that the implementation produces; copy from the actual `init` template strings (step 4) and `verify` output rows (steps 5–9) so docs stay in sync.

---

## ALGORITHM

```
1. grep src/, docs/, *.md for "connection_string"  → replace each surviving occurrence
2. grep src/, docs/, *.md for "--user-config"      → replace with "--database-config"
3. grep src/, docs/, *.md for "load_user_config"   → replace with "load_database_config"
4. open vulture_whitelist.py and delete the two lines
5. update mcp-tools-sql.md line ~859
6. update README.md Quick Start
7. add cli/ note to docs/architecture/architecture.md
8. write docs/cli.md (new)
9. run quality gates
```

---

## DATA — None

Documentation only.

---

## Tests

No new automated tests for docs. Manual verification:
- Run `mcp-tools-sql init --backend sqlite -h` and `mcp-tools-sql verify -h` and check that `docs/cli.md` matches the actual `--help` output.
- Run a full `mcp-tools-sql init --backend sqlite && mcp-tools-sql verify` against a fresh tmp dir and confirm the README Quick Start flow works exactly as documented.

---

## Quality gates

- `mcp__tools-py__run_pylint_check`
- `mcp__tools-py__run_pytest_check` (standard exclusions)
- `mcp__tools-py__run_mypy_check`
- `mcp__tools-py__run_tach_check`
- `mcp__tools-py__run_lint_imports_check`
- `mcp__tools-py__run_vulture_check` — confirm whitelist cleanup did not introduce new findings

---

## LLM Prompt for this step

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_10.md`. This is the final, documentation-only step. Update the existing-doc gaps: `mcp-tools-sql.md` line ~859 (replace the `connection_string=` example with the new `path=` / `host=`+`port=`+... shape from step 2); `README.md` Quick Start (align with the real `init`/`verify` UX delivered by steps 4–9; replace `--user-config` with `--database-config`, replace `connection_string` examples with the new fields); `docs/architecture/architecture.md` (add a short paragraph or update the layer diagram to include the new `mcp_tools_sql.cli` package between `main` and `server` per the importlinter contract); `vulture_whitelist.py` (remove the `_.connection_string` and `_.load_user_config` entries — both names are gone after steps 1–2). Create a new `docs/cli.md` CLI reference covering global flags, the `init` and `verify` commands (all flags, example output for each, exit codes 0/1/2). Cross-link from the README. Run all quality checks plus vulture and ensure they pass.
