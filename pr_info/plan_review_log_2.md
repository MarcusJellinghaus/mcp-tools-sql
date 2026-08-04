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

## Round 2 — 2026-08-04

**Findings** (6). The review agent first re-verified every round-1 edit against the live codebase and found them all internally consistent and correct (`columns=[]`/duplicate guards, param threading, `None`-distinct blanking, mypy narrowing, `DISTINCT_GATE_ROWS`, `clamp_n`, `async core` vs `tool_builder.py:33`, tach `config` removal, `exp.Length` → `LEN`/`LENGTH`, `LIMIT_IS_TOP` for tsql). New findings:
- `step_1.md:40` — medium — T-SQL `timestamp` (rowversion) misclassified as temporal. `INFORMATION_SCHEMA.COLUMNS.DATA_TYPE` reports `timestamp` for `rowversion`, which is binary(8), not date/time; `MIN`/`MAX` on it raises Msg 8117 and, since all scalar aggregates share one `SELECT`, one legacy column takes down the whole table's pass — the failure mode the LOB rule exists to prevent.
- `step_4.md:66,39-40,82` — low — `ref.is_(exp.null()).not_()` renders `NOT "c" IS NULL`, contradicting the HOW/ALGORITHM/TEST text that all say `IS NOT NULL`.
- `step_5.md:90` — low — remainder pseudocode contradicts the line below it (unbound `freq`; iterates tuples not values) on the one calculation the plan says to pin with a test.
- `step_7.md:134-138` — low — `n` is a dead parameter threaded through four renderer functions with a self-cancelling rationale.
- `step_7.md:133` — low — `ColumnProfile` construction underspecified: dict→tuple mapping unstated, and triage profiles have no stated `value_kind`/`values` on a frozen dataclass with no defaults.
- `step_1.md:30` vs `:39` — low — `NUM` is cited as the motivating affinity but the numeric token list does not match it, so it falls through to `other`.

**Decisions**: all 6 accepted. Finding 1 is a genuine correctness gap and was the round's justification; 2–6 are spec tidiness. None affect scope or architecture, so none were escalated. For finding 4 the simpler option was taken — drop the parameter rather than find a use for it.

**User decisions**: none required.

**Changes**: `step_1.md`, `step_4.md`, `step_5.md`, `step_6.md`, `step_7.md` updated; `Decisions.md` appended. `summary.md` needed no change. No implementation code touched.

**Status**: committed.
