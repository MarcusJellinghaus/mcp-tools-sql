# Plan Review Log — Issue #10 (Server setup and CLI entry point)

**Branch:** `10-server-setup-and-cli-entry-point`
**Base:** `main` (CI=PASSED, Rebase=UP_TO_DATE)
**Plan files:** `pr_info/steps/summary.md`, `step_1.md`–`step_4.md`
**Review run:** 1
**Started:** 2026-05-07

## Round 1 — 2026-05-07

**Findings (from `/plan_review` engineer subagent):**

Critical:
- C1: Step 1 lock semantics — every `execute_query` takes `_connect_lock` because the lock lives inside `connect()` and `connect()` is called on every method invocation; summary's "no double-check pattern" directive is the cause.
- C2: Step 1 hedge "drop or keep `_require_connection`" should commit to drop; new lazy-connect test only covers `execute_query` while existing test it replaces is parametrized over three methods.
- C3: Step 4 friendly-error block catches `ValueError` only, but missing-file errors raise `OSError`/`FileNotFoundError`; existing `verify.py` already catches `(ValueError, OSError)`.
- C4: Step 4 test #4 (`test_lazy_connect_constructible_when_db_unreachable`) uses `:memory:` which always succeeds — does not actually exercise lazy-connect.
- C5: Step 4 startup log: pin `connection=qcfg.connection`, not `conn.backend`.

Improvements:
- I1: `tool_logging` `tach.toml` `depends_on` should be `[]` (module body uses only stdlib).
- I2: Step 3 contradicts summary on `tach.toml` deps for tool modules — summary says all four, Step 3 footnote says `schema_tools` only.
- I3: Step 2 should require `@pytest.mark.asyncio` (drop `asyncio.run` fallback).
- I4: Step 2 — add docstring warning that `log_tool_call` DEBUG output contains param values + resolved SQL.
- I5: Step 3 — drop FastMCP plumbing alternative; commit to direct `_build_tool_fn` invocation.
- I6: Step 4 — add a setup_logging-before-run_server ordering assertion.
- I9: Step 2 — module docstring distinguishing from `utils/log_utils.py`.

Questions for user (Q1, Q3) — others auto-triaged.

**Decisions:**

| Finding | Decision |
|---|---|
| C1 / Q1 | Asked user — chose **double-checked locking** (fast path + locked first-call). |
| C2 (drop helper) | Accept; instruct engineer to drop `_require_connection` unconditionally. |
| C2 (parametrize test) | Accept; parametrize new test over `(execute_query, execute_update, explain)`. |
| C3 / Q3 | Asked user — chose **`(ValueError, OSError)`** (matches `verify.py` pattern). |
| C4 | Accept; rewrite test #4 with unreachable parent dir + connect-counter assertion. |
| C5 | Accept; add comment pinning connection-name source in ALGORITHM. |
| I1 / Q5 | Accept; `depends_on = []` for `tool_logging`. |
| I2 / Q2 | Accept; align Step 3 with summary — add `tool_logging` to all four tool-implementation modules. |
| I3, I4, I5, I6, I9 | Accept; instruct engineer to apply each. |
| I7 | Accept; folded into C2 fix. |
| I8 | No fix needed. |

**User decisions:**
- Q1 (lock semantics): **Double-checked locking** — fast path returns when `_connection` is set and not closed; lock acquired only on first-call. Honors issue's "first-calls" race wording.
- Q3 (error catch): **`(ValueError, OSError)`** — uniform UX with `verify.py`; covers missing-file errors as friendly stderr + exit 2.

**Changes (via `/plan_update` engineer subagent):**

- `pr_info/steps/summary.md` — lock paragraph rewritten for double-checked locking; `tool_logging` description updated to `depends_on = []`; exit-code table row covers `ValueError`/`OSError`.
- `pr_info/steps/step_1.md` — `connect()` algorithm fast-path + locked region; drop `_require_connection`; `test_lazy_connect_on_first_call` parametrized over three methods.
- `pr_info/steps/step_2.md` — `tach.toml` `depends_on = []`; `@pytest.mark.asyncio` required; module docstring + `log_tool_call` PII docstring spelled out.
- `pr_info/steps/step_3.md` — direct `_build_tool_fn` invocation only; `tach.toml` adds `tool_logging` to all four tool-implementation modules; KISS footnote removed.
- `pr_info/steps/step_4.md` — `except (ValueError, OSError)`; test #4 rewritten with unreachable parent dir + connect-counter; setup_logging ordering test added; startup-log connection-name source pinned; bad-config test parametrized over three scenarios.

**Status:** plan changes ready; commit agent dispatched.

## Round 2 — 2026-05-07

**Findings:** none. Engineer verified each round-1 change landed correctly:
- Step 1 double-checked locking algorithm correct; `RuntimeError` raised inside locked region post-close.
- Step 1 parametrized lazy-connect test references real fixtures/helpers (`_make_backend`, `sqlite_db`, `_DATA_METHODS`).
- Step 3 `tach.toml` snippet matches current state for all four tool-implementation modules.
- Step 4 parametrized bad-config test maps scenarios to correct exception classes (`FileNotFoundError` ⊂ `OSError`; `ValueError` for the others).
- Issue #10 `## Scope` checkboxes all covered; step DAG valid; no YAGNI violations.

**Decisions:** N/A — nothing to address.

**User decisions:** N/A.

**Changes:** none.

**Status:** zero plan changes — loop terminates.

---

## Final Status

- **Rounds run:** 2
- **Plan-file commits produced:** 1 (`8e51070` — round 1)
- **User design questions asked:** 2 (lock semantics → double-checked locking; error catch → `(ValueError, OSError)`)
- **Verdict:** plan approved — ready for implementation.
- **Next step:** dispatch implementation per `pr_info/steps/step_1.md` → `step_4.md`. Steps 1 and 2 are independent and can run in parallel; step 3 needs step 2 merged; step 4 needs step 1 merged.
