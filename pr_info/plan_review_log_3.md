# Plan Review Log 3 — Issue #8 (validate_sql)

Third supervisor run. Plan was previously reviewed and finalised across two prior supervisor sessions (see `plan_review_log_1.md` and `plan_review_log_2.md`). Round 2 of run 2 ended with zero findings. This run starts a fresh `/plan_review` to verify nothing has regressed and the plan is still implementation-ready, looping until a round produces zero plan changes.

## Round 1 — 2026-05-15

**Findings** (from engineer's `/plan_review`): six nit-level findings, zero blockers/should-fix.
- F1 — `Decisions.md` is incomplete relative to its title (only #8 and #9 captured; #1–#7, #10–#18 live in issue body without a pointer)
- F2 — Possible strict-mypy override-signature mismatch on `get_isolated_connection` (abstract `AbstractContextManager[Any]` vs concrete `Iterator[Any]` via `@contextmanager`)
- F3 — SQLite "borrowed connection" contract not explicit in the abstract docstring (callers must not close)
- F4 — `params or {}` consistency missing in pre-flight spec (`extract_param_names(sql) - params.keys()` breaks when `params is None`)
- F5 — Missing test bullet: SQL has `:a` and `params={"a": 1, "b": 2}` (extra `b` alongside parameterised SQL)
- F6 — `_count_statements` reports `";;"` as 2 statements; HOW says pure-punctuation falls through — minor mismatch worth a one-line acknowledgement

**Decisions** (supervisor triage):
- F1 → accept (one-line scope preamble in `Decisions.md`)
- F2 → accept (pick a resolution in the plan so the implementer doesn't have to decide at code-write time)
- F3 → accept (one sentence in the abstract docstring)
- F4 → accept (algorithm wording fix)
- F5 → accept (add test bullet)
- F6 → accept (one-line note in HOW)

All six are clarifications, test additions, or docstring tightenings — none affect scope or architecture. No design questions; nothing to ask the user.

**User decisions:** none.

**Changes applied:**
- C1 — `Decisions.md`: scope preamble added under the title noting this file holds #8 and #9 (added/refined during plan review); #1–#7 and #10–#18 live in the issue body.
- C2 — `step_1.md`: chose **Option A** (abstract method returns `AbstractContextManager[Any]` as a plain method; concrete impls use `@contextmanager` but annotate their public return as `AbstractContextManager[Any]` with `# type: ignore[misc]`). Picked after reading `src/mcp_tools_sql/backends/base.py` and confirming no existing `@contextmanager` convention. Updated the WHAT code blocks and imports bullet for consistency; `summary.md` already aligned and was not touched.
- C3 — `step_1.md`: appended "Callers MUST NOT close the yielded connection; the backend owns its lifecycle." to the abstract method docstring, adjacent to the SQLite-no-op / MSSQL-close-on-exit description.
- C4 — `step_2.md`: `_preflight` algorithm bullet reworded to `extract_param_names(sql) - (params or {}).keys()` with a parenthetical noting `params` may be `None`.
- C5 — `step_2.md`: added a Param-handling test bullet for `SELECT :a` with `params={"a": 1, "b": 2}` → `Valid.`, exercising set-difference tolerance for extras when the used set is non-empty.
- C6 — `step_2.md`: appended one-line note to the pure-punctuation HOW bullet — `";;"` parses as two punctuation-only statements, so it returns the multi-statement verdict (consistent and acceptable).

**Files changed:**
- `pr_info/steps/Decisions.md`
- `pr_info/steps/step_1.md`
- `pr_info/steps/step_2.md`

**Status:** changes applied; commit pending.

## Round 2 — 2026-05-15

**Findings** (from fresh engineer's `/plan_review`): none — plan is implementation-ready.

The round-1 fixes (C1–C6) all landed cleanly and the engineer surfaced no new issues on independent inspection. Verified specifically:
- Decision #9 reconciliation (synthetic `ValidationError:` prefix for pre-flight vs `<ExcType>:` for caught exceptions) is consistent across Step 2's pre-flight messages and tests.
- Step 1's Option A mypy resolution (abstract returns `AbstractContextManager[Any]`; concrete impls annotated the same with `# type: ignore[misc]`) is correctly explained.
- Step 2's exception-ladder ordering, SHOWPLAN `finally` pattern, `_count_statements` / `_first_keyword` edge-case handling (including `";;"` → multi-statement verdict) are coherent.
- Step 3a's `_PROGRAMMATIC_BUILTIN_TOOLS` placement in `schema_tools.py` preserves `server` → `schema_tools` one-way dependency; `load_default_queries(path: Path | None = None)` injection seam is consistent with the collision-skip test.
- Step 3b's session-state containment surrogate (`DB_NAME()`) is appropriate now that `USE` pre-flight rejection eliminates the original "USE slipped past" scenario.
- Step ordering / one-commit-per-step / passing checks at each step boundary intact.

**Decisions:** none — no findings.

**User decisions:** none.

**Changes applied:** none.

**Files changed:** none (only this log entry).

**Status:** no plan changes needed.

## Final Status

Two rounds in this supervisor session.

- **Round 1** — six nit-level findings, all autonomously triaged and applied (no user decisions required): scope preamble in `Decisions.md`; Option A mypy resolution + "borrowed connection" docstring in `step_1.md`; `params or {}` consistency, extra-params-with-parameterised-SQL test bullet, and `";;"` multi-statement acknowledgement in `step_2.md`. Committed as `ff3ca22` — `docs(plan): apply round-3 plan-review clarifications for validate_sql`.
- **Round 2** — zero findings. Loop terminates.

The plan remains implementation-ready. No outstanding design questions. Plan files: `summary.md`, `step_1.md`, `step_2.md`, `step_3a.md`, `step_3b.md`, `Decisions.md`. Implementation order is 1 → 2 → 3a → 3b, each producing exactly one commit and leaving the codebase with passing checks.
