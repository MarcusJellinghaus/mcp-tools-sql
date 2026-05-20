# Plan Review Log — Issue #21

**Issue:** Extract verify logic from `cli.commands` into `mcp_tools_sql.verification`
**Branch:** `21-extract-verify-logic-from-cli-commands-into-mcp-tools-sql-verification`
**Base:** `main` (up-to-date, CI passing)
**Plan files:** 10 step files + `summary.md`
**Task tracker:** empty (no implementation has started)

## Round 1 — 2026-05-20

**Findings (engineer review):**
- `_entry` is `_`-prefixed but imported cross-module by 8 section files → pylint protected-access friction
- Step 9 should explicitly drop the now-dead `_entry` import from the slim shim
- Step 9 should consider pruning `cli.commands.depends_on` in `tach.toml` (entries unused after the shim trim)
- Step 6: `test_connection.py` missing `SQLiteBackend` import for the success-path test
- Step 7: `test_queries.py` missing `MSSQLBackend` import for the unimplemented-backend test
- Step 9 algorithm pseudocode does not call out the silent-skip when `qcfg is None` on the happy path (matches current behaviour but worth a NOTE)
- Step 9 should add a `check_file_size` Check for the trimmed `tests/cli/test_verify.py` (currently 1336 lines)
- Step 1 should sanity-check that other test subpackages use `__init__.py` before creating `tests/verification/__init__.py`
- Verified: `.importlinter` "above vs below" correction is correct in Step 1
- Verified: `sqlite_db` fixture deviation (keep at `tests/conftest.py` root) is correct in Step 1 and the conftest

**Decisions:**
- **Accept:** missing test imports (steps 6, 7); `qcfg is None` NOTE (step 9); file-size assertion + trim target (step 9); `tests/verification/__init__.py` convention check (step 1); drop dead `_entry` import in slim shim (covered by Update 1 rename + Update 2 audit)
- **Ask user:** `_entry` rename; tach prune in step 9
- **Skip:** out-of-scope file list in summary (pre-existing issues per principles); step 3 fixture duplication (works as-is); `verify_one_query/update` underscore rename (issue explicit on "submodule-internal" convention)

**User decisions:**
- Q1 (`_entry` naming): **Rename to `make_entry`** — applied across `summary.md` and steps 1–9; `VerifierEntry` TypedDict keeps its name
- Q2 (tach `cli.commands.depends_on` cleanup): **Prune in step 9** with a mandatory `search_files` safety check across `src/mcp_tools_sql/cli/commands/*.py` before removing each entry; entries targeted for removal: `backends`, `schema_tools`, `query_helpers`, `tool_builder`, `formatting`

**Changes:**
- `pr_info/steps/summary.md`, `step_1.md` through `step_9.md` updated (10 files total; `step_10.md` untouched — documentation-only step with no `_entry` references)
- `step_1.md` gains a rename-rationale subsection and a `tests/verification/__init__.py` convention-check note
- `step_9.md` gains: tach-prune HOW subsection with safety check + full diff; `qcfg is None` NOTE in algorithm pseudocode; `check_file_size` Checks for both the slim shim (~150 lines) and the trimmed test file (~300 lines); re-runs of `run_tach_check` and `run_lint_imports_check`
- Imports added in `step_6.md` (`SQLiteBackend`) and `step_7.md` (`MSSQLBackend`)

**Status:** committed (`3889166`)

## Round 2 — 2026-05-20

**Findings (engineer re-review):**
- All seven round-1 updates verified clean (no orphaned `_entry`, paths correct, NOTES in place, file-size Checks present, convention note recorded)
- **New:** step 9 prune list omits `utils`, but a fresh grep across `src/mcp_tools_sql/cli/commands/*.py` finds zero usages of `mcp_tools_sql.utils` — the plan's own safety-check rule would also prune it
- **New:** step 1 rename-rationale says "The original CLI module name was `_entry`" — `_entry` is a function, not a module; copy-edit needed
- **New:** step 9 LLM Prompt lists the helpers kept in the slim shim but doesn't say "preserve verbatim" — matters because `_print_and_summarize` controls the byte-exact snapshot test output

**Decisions:**
- **Accept all three:** straightforward improvements, no user input needed
- **Skip:** none

**User decisions:** none required this round

**Changes:**
- `step_9.md`: added `utils` to the prune-candidate list (Modified-files bullet, HOW prose, safety-check `search_files` comment, LLM Prompt step 7); updated post-prune `tach.toml` diff so `cli.commands.depends_on` is `{cli, config, verification}`; appended a sentence to LLM Prompt step 4 requiring verbatim preservation of `_pad`, `_format_row`, `_print_section`, `_compute_exit_code`, `_print_and_summarize`
- `step_1.md`: corrected rename-rationale wording from "original CLI module name was `_entry`" to "The original helper function was named `_entry`"

**Status:** committed (`4e60af5`)

## Round 3 — 2026-05-20

**Findings (convergence check):**
- All three round-2 updates verified correctly applied (utils-prune consistent across Modified-files / HOW / safety-check / LLM Prompt / tach.toml diff; rename-rationale wording fixed; verbatim-preservation sentence present with all five helpers and rationale)
- Cross-check: `summary.md`'s `verification` module `depends_on` line (`[backends, config, schema_tools, query_helpers, utils]`) is about the new module — not contradicted by the `cli.commands.depends_on` prune (different module)
- No new issues introduced by round-2 edits
- No critical issues, no auto-acceptable improvements, no design questions

**Decisions:** none — convergence reached

**User decisions:** none required

**Changes:** none (zero plan files modified)

**Status:** convergence — review loop terminates

## Final Status

**Result:** Plan is ready for approval.
**Rounds run:** 3 (rounds 1 and 2 produced changes; round 3 produced none — convergence).
**Commits produced (plan files):** `3889166`, `4e60af5` (this log committed separately).
**Total plan-file edits across rounds:** 10 files round 1, 2 files round 2.
**Open questions for user:** none.
**Next step:** approval / status promotion to start implementation.
