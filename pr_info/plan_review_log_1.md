# Plan Review Log 1 — Issue #37

Branch: `37-default-server-logging-to-file-under-mcp-tools-sql-logs-with-output-level-console-output`
Base: `main` (up to date)
Plan: `pr_info/steps/summary.md`, `step_1.md` … `step_6.md`
Task tracker: empty — no steps implemented yet, full plan under review.

## Round 1 — 2026-08-26

### Findings

1. **critical** — `step_1.md` exit criteria cannot detect the failure Step 1 most plausibly causes: pylint/pytest/mypy never re-resolve dependencies, so the new `>=0.1.6.dev0` floor can be unsatisfiable in CI *and* in `tools/reinstall_local.sh` (which installs the project at step 2/5, before the GitHub overrides at step 3/5) while the step still reports green.
2. **critical** — `step_5.md` (old) contradicted Decision 8: `logger.log(OUTPUT, ...)` is level 25, so a startup failure never reaches the log file at `--log-level WARNING` or `ERROR`.
3. **worth-fixing** — Releasing mcp-coder-utils 0.1.6 upstream would delete Step 1 entirely (floor, five CI edits, two `pyproject.toml` uncomments, the follow-up "relax the floor" chore).
4. **worth-fixing** — The venv upgrade was an unnumbered "step 0" floating outside the step structure, duplicated as banners in `step_3.md` and `step_4.md`; `planning_principles.md` disallows preparation steps.
5. **worth-fixing** — `summary.md` and `step_1.md` referenced `./tools/format_all.sh`, which does not exist (`tools/` holds only `check_no_url_deps.py`, `read_github_deps.py`, `reinstall_local.bat`, `reinstall_local.sh`).
6. **worth-fixing** — `step_6.md` exit criteria prescribed a raw Bash `mcp-coder check file-size …` where CLAUDE.md mandates `mcp__mcp-workspace__check_file_size`.
7. **worth-fixing** — `step_1.md` exit criteria wrote `mcp__tools-py__…` instead of `mcp__mcp-tools-py__…`; Steps 2–6 spelled it correctly.
8. **worth-fixing** — `step_4.md` test 3 parametrized `server` only; nothing asserted end to end that `init`/`verify` reach `setup_logging` with `log_level="OUTPUT"` and `console_level=None`.
9. **worth-fixing** — `--console-only --log-level ERROR` would have hidden the friendly startup error that `print()` always showed; undocumented regression.
10. **cosmetic** — `step_5.md` (old) was a two-line source change plus one test migration, intertwined with Step 4's `console_level` wiring.
11. **cosmetic** — `step_6.md` §5 scoped out the stale `--project-dir` at `mcp-tools-sql.md:718` but never mentioned the second occurrence at `:852`.

Verified accurate and left alone: every line reference in the plan (`main.py:104/106/115-118/117`, `init.py:226`, `loader.py:128`, `config_files.py:68`, `ci.yml` 88/116/154/204/251, `docs/cli.md:20-23`/`:31-33`, `README.md` 40→62, `mcp-tools-sql.md:709-711`/`:718`, `architecture.md` §6), the `tach.toml` gap, the `tests/*/__init__.py` convention, and that the installed mcp-coder-utils really is pre-`console_level`. The empty `TASK_TRACKER.md` is correct per `planning_principles.md` and was not treated as a finding.

### Decisions

- 1 — **accept (mechanical half)**. Added the verification exit criteria and an "Install-order risk" section; scoped a `reinstall_local.sh`/`.bat` reorder into Step 1 conditional on the verification failing.
- 2 — **ask user**. Escalated; answered below.
- 3 — **ask user**. Escalated; answered below.
- 4, 5, 6, 7, 8, 10, 11 — **accept**. All mechanical, applied as described under Changes.
- 9 — **accept, closed by the finding-2 fix**. `logger.error` passes a console threshold of `ERROR`, so no separate change was needed.

### User decisions

- **Finding 3 — rejected (Option B: keep Step 1 as planned).** mcp-coder-utils 0.1.6 is being released independently and in parallel, so the floor, the five CI install-site edits and the `[tool.uv.sources]` / `[tool.mcp-coder.install-from-github]` uncomments all stay. No caveat about PyPI resolvability is to appear in the plan, and the question is not to be re-litigated.
- **Finding 2 — Option D: `mcp_coder`'s split pattern.** `logger.error("%s", exc)` for the exception text, `logger.log(OUTPUT, ...)` for the follow-up hint, and drop the `"Error: "` literal because `CleanFormatter` supplies the `ERROR: ` prefix (`mcp_coder_utils/log_utils.py:90-91`). Basis: `mcp_coder` uses exactly this two-line shape in five places (`cli/main.py:203-207`, `:233-238`, `:256-258`, `:276-277`, `:291-292`) and logs bare exceptions for the same formatter reason (`commit.py:85`, `:99`, `:119`). The two sisters offered no precedent — `mcp-workspace/main.py:212-215`, `:222-225`, `:259-261` and `mcp-tools-py/main.py:122-125` all still `print()` to stdout.

### Changes

- `summary.md` — §4 rewritten for the `logger.error` + `logger.log(OUTPUT, ...)` split, with a per-sink threshold table and the `"Error: "` rationale; §6 absorbed the venv upgrade into Step 1; the standalone "Prerequisite" section removed; step table cut from six rows to five; Modified-files table Step column renumbered and the two `main.py` rows merged; `tools/reinstall_local.*` added as a conditional Step 1 file; `format_all.sh` → `mcp__mcp-tools-py__run_format_code`.
- `step_1.md` — WHAT split into three numbered parts, the third being the venv upgrade; new "Install-order risk — verify, do not assume" section; exit criteria now require `reinstall_local.sh` to succeed, `uv pip show mcp-coder-utils` to satisfy the floor, and the installed `setup_logging` to accept `console_level`; tool-name prefixes and `format_all.sh` fixed; LLM prompt extended.
- `step_3.md` — prerequisite banner and the LLM-prompt venv check removed; the "that is Step 5" pointer redirected to Step 4.
- `step_4.md` — retitled and rescoped to absorb the old Step 5; hard-prerequisite banner removed; new "server error branch through the logger" section with the split pattern, ecosystem citations and the two consequences; ALGORITHM extended; test 3 gained a `verify` row plus an `expected_log_level` column and a `verify_cmd.run` stub; the migrated `caplog` test folded in as test 4, asserting on `levelname == "ERROR"` plus the hint text rather than an `"Error:"` literal (avoiding an `import logging`); exit criteria and LLM prompt updated.
- `step_5.md` — deleted (merged into Step 4).
- `step_6.md` → `step_5.md` — renumbered throughout; `docs/cli.md` Logging draft gained the "failed launch is logged at `ERROR`" sentence plus a note not to promise the hint; §5 now acknowledges both stale `--project-dir` occurrences (`:718` and `:852`); architecture bullets gained the error-path line; file-size exit criterion switched to `mcp__mcp-workspace__check_file_size`.

No `pr_info/steps/Decisions.md` was created — this log carries the round's decisions, and issue #37's own Decisions table remains the canonical record.

### Status

All 11 findings resolved: 9 applied, 1 rejected by user decision (finding 3), 1 closed as a side effect (finding 9). Plan is now five steps. No source or test files were touched. Not committed.
