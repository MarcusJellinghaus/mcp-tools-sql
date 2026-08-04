# review-plan review log 2

Issue #43 — `summarize_columns`: per-column data profiling tool
Branch: `43-summarize-columns-per-column-data-profiling-tool`
Started: 2026-08-04
Context: continues after `plan_review_log_1.md` (4 rounds, all findings applied).
Implementation not started (TASK_TRACKER: 0 of 7 steps complete).

## Round 1 — 2026-08-04

**Findings** (12; review agent verified plan claims against the live codebase and empirically against sqlglot 30.14 / sqlite 3.46):
- `step_7.md:99-104` + `step_6.md:70` — medium — empty `columns=[]` unhandled; `build_scalar_sql([])` renders `SELECT FROM "t"`. `render_summary`'s `if not profiles: return ...` left as a literal ellipsis.
- `step_7.md:40-48` — medium — round-4 param-threading fix is spec-only; no test binds `where` + `:name` + `params` end-to-end. Wording at :43-44 wrong (unfiltered count carries no placeholders).
- `step_6.md:37-41` — medium — triage `distinct` cell undefined when `None`; `other`/binary columns get no `COUNT(DISTINCT)` even ungated, so tabulate prints `None`.
- `step_5.md:20,73-77` + `step_7.md:79` — low — `distinct: int | None` / `values: list | None` used unguarded; mypy strict would fail.
- `summary.md:146` vs `step_5.md:22` — low — contradictory `values` annotation.
- `step_7.md:69` — low — 1M distinct gate is an inline literal, untested despite being listed as a tested invariant.
- `step_7.md:30-37,93` — low — no tool description string specified (required by `build_tool_fn`/`add_tool`); `log_tool_call` usage underspecified.
- `step_4.md:17` — low — `clamp_n` clamps only upward; `n=0`/`n<0` broken.
- `step_7.md:30` — low — `core` not `async` though `build_tool_fn` awaits it.
- `step_7.md:103` — low — duplicate names in `columns` not de-duplicated; can flip a 15-name call into triage.
- `step_7.md:116` — low — tach `depends_on` still lists `config` (raised in round 4 of log 1, never applied).
- `step_1.md:81-82` + `step_7.md:177` — low — PROMPTs reference nonexistent pytest "fast markers".

**Decisions**: all 12 accepted. None affect scope or architecture — they are spec gaps, internal contradictions, and missing plan-level tests, so none were escalated. Two judgement calls delegated to the engineer and accepted: `rec.record(rows=len(profiled), cols=1)`, and `DISTINCT_GATE_ROWS` placed in `render.py` beside `TRIAGE_THRESHOLD`/`COLUMN_CAP` (triage-view concept).

**User decisions**: none required.

**Changes**: `step_1.md`, `step_4.md`, `step_5.md`, `step_6.md`, `step_7.md`, `summary.md` updated; `Decisions.md` created logging all 12 with rationale. No implementation code touched.

**Status**: committed.
