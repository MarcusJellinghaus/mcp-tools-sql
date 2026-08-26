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

## Round 2 — 2026-08-26

Plan re-reviewed fresh at five steps (`summary.md`, `step_1.md` … `step_5.md`).
Round 1's two settled decisions — keeping Step 1 rather than waiting on an
upstream 0.1.6 release, and `mcp_coder`'s `logger.error` / `logger.log(OUTPUT, …)`
split for the friendly-error branch — were treated as closed and not re-opened.

### Findings

1. **worth-fixing** — `step_3.md`'s new autouse fixture `no_op_setup_logging` in
   `tests/cli/conftest.py` is never named as a parameter by any test, so vulture
   reports `unused function 'no_op_setup_logging' (60% confidence)` — exactly the
   `--min-confidence 60` the `architecture` CI job uses. Step 3 lists vulture as
   an exit criterion it must pass, but neither its WHERE section nor
   `summary.md`'s Modified table mentioned `vulture_whitelist.py`. Confirmed by
   probe, not analysis: vulture flags it at a realistic `tests/cli/conftest.py`
   path (exit 3), and an attribute-style whitelist entry suppresses it (exit 0).
   `redirect_home_and_cwd` in `tests/cli/test_init.py` is not precedent — several
   tests request it by name, so vulture already counts it as used.
2. **cosmetic** — `step_5.md` §4: the README draft's ` ```markdown ` fence
   contains a ` ```bash ` fence, so the outer fence closed early at the inner
   terminator. Two lines of the draft fell outside it and the closing fence
   opened a new block that swallowed the `### 5.` heading.
3. **cosmetic** — `step_4.md` Tests §2 used `fnmatch(resolved.name, …)` without
   listing `from fnmatch import fnmatch`, while Test §4 separately enumerates the
   module's imports to justify avoiding `import logging`.
4. **cosmetic** — `step_4.md` Tests §4: prose said "Assert on the **exception
   text**" but the sample asserts a level name (`"ERROR" in levels`).
5. **cosmetic** — `step_1.md` exit criteria: "(unchanged from baseline — this
   step touches no Python)". The step swaps the installed mcp-coder-utils for git
   `main`, which changes `setup_logging` at runtime, so the baseline can shift and
   the parenthetical invites dismissing a real failure.
6. **cosmetic** — issue #37's Decision 6 includes "add a note to #35 that
   `docs/mcp-clients.md` should mention the log location". `summary.md` described
   it as a follow-up but no one owned it.

Verified accurate and left alone: upstream `mcp-coder-utils` `main` matches the
plan exactly — the `if console_level is not None or not log_file:` gate,
`console_handler.setLevel(numeric_console_level)`, the formatter chosen from the
*console* level (`CleanFormatter` at ≥ `OUTPUT`, so the dropped `"Error: "`
literal is correct), the `min()` root floor, `_HANDLER_MARKER` idempotency,
unconditional `structlog.configure`, and `logging.addLevelName(25, "OUTPUT")` at
import. The installed venv really is pre-`console_level`. Every line reference
holds: `main.py` 103/104/106/117, the three and only three `Path.home()` path
constructions (`init.py:226`, `loader.py:128`, `config_files.py:68`), the five
`ci.yml` install sites (88/116/154/204/251) with the tabulated extras,
`docs/cli.md` 20-23 and 31-33, README Quick Start ending 60 / Configuration 62,
`mcp-tools-sql.md` 706-712 / 718 / 852, `architecture.md` §4 and §6. `tach.toml`'s
`cli.commands` really lacks `utils` while `main` already has it. `args.log_level`
is read only in `main.py`, so `default=None` cannot leak into `run_server`. Every
`main()` call in the suite lives under `tests/cli/`, so the autouse fixture covers
them all and Step 4's "no log files in the developer's home" criterion is
achievable. The four server-path functions / six invocations count is exact.
`docs/cli.md` has no existing `Logging` heading, so the `#logging` anchor is
unique. No stale `step_6` references or renumbering leftovers survive round 1's
merge. The empty `TASK_TRACKER.md` remains correct per `planning_principles.md`.

### Decisions

- 1, 2, 3, 4, 5 — **accept**. All mechanical, applied as described under Changes.
- 6 — **accept, but deliberately not assigned to a step.** It is a GitHub comment
  on another issue, not a commit on this branch, so it stays outside the step
  structure and is recorded as a manual action instead.

### User decisions

None this round. No finding required escalation.

### Changes

- `vulture_whitelist.py` — `_.no_op_setup_logging` added under "FALSE POSITIVES -
  Pytest Fixtures", with a comment explaining why it is needed and contrasting it
  with `redirect_home_and_cwd`, so it is not later removed as noise. Re-ran
  vulture: still silent.
- `step_3.md` — `vulture_whitelist.py` added to WHERE/Modified, noting the entry
  is already in place on the branch and must be kept, with the reason.
- `summary.md` — Modified table gained a `vulture_whitelist.py` row at Step 3;
  "Follow-up not covered here" rewritten as an explicit post-merge manual action
  for Marcus, stating that no step owns it and an implementing agent must not post
  the comment.
- `step_4.md` — Tests §2 switched from `fnmatch` to `startswith` / `endswith`,
  with a note saying why (keeps the module's import list as Test §4 assumes);
  Tests §4 prose rewritten to say it asserts the record's **level name**, with the
  specificity argument (`tool_logging.py:79` is the only other `logger.error` in
  `src/` and cannot fire on this path). Sample code left unchanged.
- `step_5.md` — §4's README draft rewrapped in a four-backtick fence so the inner
  ` ```bash ` block no longer terminates it.
- `step_1.md` — exit-criteria parenthetical replaced with an explicit warning that
  the dependency swap changes `setup_logging` at runtime, so a check failure here
  is a real signal.

No `pr_info/steps/Decisions.md` was created — consistent with round 1, this log
carries the round's decisions and issue #37's Decisions table remains canonical.

### Status

All 6 findings resolved: 5 applied as mechanical plan edits, 1 (finding 6)
accepted and recorded as a manual post-merge action rather than a step. Plan
remains five steps. One non-plan file was touched — `vulture_whitelist.py`, the
fix for finding 1; no other source or test file was changed. Not committed.

## Final Status

Three review rounds run. Round 1: 11 findings. Round 2: 6 findings. Round 3:
zero findings — the loop terminated on a clean round.

Commits produced: `75bcc99` (round 1), `a7cc346` (round 2).

### Plan shape

Started at six steps, now five. The old `step_5.md` (server error path) was
merged into `step_4.md`; the old `step_6.md` (docs) was renumbered to
`step_5.md`.

### Escalated design decisions

- **Step 1 kept.** The `mcp-coder-utils>=0.1.6.dev0` floor, the five CI
  git-install sites and the two `pyproject.toml` uncomments all stay.
  mcp-coder-utils 0.1.6 is being released upstream independently, so no caveat
  about PyPI resolvability appears in the plan.
- **Friendly-error branch uses `mcp_coder`'s split pattern.**
  `logger.error("%s", exc)` for the exception text, `logger.log(OUTPUT, ...)`
  for the hint, and the `"Error: "` literal dropped — `CleanFormatter` supplies
  the `ERROR: ` prefix.

### Requirement-level change landed ahead of implementation

`vulture_whitelist.py` gained `_.no_op_setup_logging`, with a comment
explaining why it is needed. Step 3 must keep it.

### Outstanding manual action for Marcus

No step owns it, and no implementing agent should do it: post a comment on
issue #35 that `docs/mcp-clients.md` should mention the server log location
(`~/.mcp-tools-sql/logs/mcp_tools_sql_<timestamp>.log`, one per launch).

### Verdict

Plan is implementable as written. Ready for approval.
