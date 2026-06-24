# Plan Review Log #1 — Issue #38

**Issue:** Add `count_records` tool + migrate SQL parsing from `sqlparse` to `sqlglot`
**Branch:** `38-add-count-records-tool-migrate-sql-parsing-from-sqlparse-to-sqlglot`
**Base:** `main` (up to date, no rebase needed)
**Plan state at start:** 5 steps, no steps completed (fresh plan)

---

## Round 1 — 2026-06-24

**Findings** (from `/plan_review`):
- [Straightforward] Step 1↔4 placeholder ordering risk — only single-placeholder round-trip tested; need multi-placeholder ordered assertion.
- [Straightforward] Step 1 placeholder node-type (`exp.Placeholder` vs `exp.Parameter`) spike mentioned but not gated by exit criteria.
- [Straightforward] `basic_preflight` refactor was introduced in Step 5, re-editing the same function built in Step 2 (double-edit across commits).
- [Straightforward] Step 2 SHOWPLAN test churn — render expectation of `SELECT :a`+`{"a":1}` under tsql unspecified.
- [Straightforward] Step 5 missing SQLite e2e test for duplicate/unnamed output columns in the COUNT wrapper.
- [Straightforward] Step 3 noted independent of 1–2 — confirmed deliberate, no action.
- [Design] Step 4 read-only root allow-list left with trailing `...` (the primary security boundary was unfinished).
- [Design] `count_records` executes & leaks cardinality with no auth gating.
- [Design] MSSQL leading-`WITH` rejection could false-positive on `WITH (NOLOCK)` table hints.
- [Design] Fail-closed parse makes `validate_sql` stricter (user-visible behavior change).

**Decisions**:
- Accepted all straightforward fixes (missing tests, spike gating, step restructuring, clarification).
- Step 4 allow-list: directed to finalize as a **strict fail-closed allow-list** (reject unknown roots) — this is what the issue already mandates, so applied directly rather than escalated.
- MSSQL `WITH (NOLOCK)`: genuinely new correctness refinement, in scope — directed precise `isinstance(..., exp.With)` check + negative test (autonomous).
- The other three "design" findings (auth gating, fail-closed for `validate_sql`) are **explicitly decided in issue #38** — not re-litigated, no user escalation, no plan change.

**User decisions**: None — no questions escalated (all design points already settled by the issue).

**Changes**: Updated `step_1.md`, `step_2.md`, `step_4.md`, `step_5.md`, `summary.md` via `/plan_update` (multi-placeholder ordered test; node-type spike gating; `basic_preflight` moved to Step 2; SHOWPLAN render clarified; strict fail-closed root allow-list; precise leading-`WITH` check + `WITH (NOLOCK)` negative test; duplicate-column e2e count test; summary step-overview fixed).

**Status**: Plan changed this round → committing, then looping for a fresh review round.
