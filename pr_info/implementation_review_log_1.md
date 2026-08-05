# review-implementation review log 1

## Round 1 — 2026-08-05
**Findings**:
I'll gather context in parallel: knowledge base, the issue, pr_info, and the git diff.I'll read the knowledge base files, the rest of the issue, and the summary in parallel.Now let me compute the diff against main. Let me check the branch state and the diff.Real implementation changes exist. Let me read the implementation and the reference template in parallel.Let me review the registration wiring, config changes, and tests.Let me pin down exact line numbers for the findings.I've reviewed the full diff against `main` — this is a real implementation of `summarize_columns` (new `summarize` package + wiring). Code closely follows the `count_tools` template and the design in `summary.md`; SQL generation, fail-closed `where`, identifier quoting, distinct gating, and dispatch are all sound. A few substantive issues:

src/mcp_tools_sql/summarize/tools.py:399 — medium — `clamp_note` is concatenated directly onto `render_summary(...)` with no separator, so a non-empty note (any out-of-range `n`) is glued onto the final rendered line (e.g. a value row becomes `    R6Requested n=999 exceeds the maximum 50; using 50.`). Needs a `\n\n` separator when the note is non-empty. Tests miss this because they only assert substring presence (`test_unique_key_column_sample_header_count` even splits on `"Requested n="`).

src/mcp_tools_sql/summarize/render.py:170 — medium — float stats (`mean`, `len_avg`, `size_avg`) render at full float precision via `f"{value:,}"`, so real data yields output like `avg 18.666666666666668`, diverging from the contract's documented `avg 11.4` / `mean` examples. Percentages are rounded to 1 decimal but these stat cells are not; the E2E tests only use round values (3.0/5.0) so the divergence is uncovered.

src/mcp_tools_sql/summarize/tools.py:366 — low — the clamp note is appended in the triage view and whenever no value list is rendered (all-`other`/all-null deep columns), i.e. cases where `n` never applied — a note about value-list length surfaces where nothing used it, which is misleading.
**Decisions**:
Verdict(decision='tasks', tasks=["Fix the missing separator at src/mcp_tools_sql/summarize/tools.py:399: when clamp_note is non-empty, join it to the render_summary(...) output with a '\\n\\n' separator so the note is not glued onto the final rendered line; add/adjust a test to assert the separator rather than mere substring presence.", "Fix float stat formatting at src/mcp_tools_sql/summarize/render.py:170: round/format float stats (mean, len_avg, size_avg) to the contract's precision (1 decimal, matching the documented 'avg 11.4' examples) instead of full float precision, and add a test with non-round data to cover it."], escalate_reason=None)
**Changes**:
applied

## Round 2 — 2026-08-05
**Findings**:
I'll gather context. Let me start by exploring the knowledge base, plan files, and the git state.I'll read all knowledge base files, the plan summary, and check git state in parallel.Now let me read the issue and the plan files, and check git state.Let me read the rest of the issue, the summary, and determine the branch.Now let me compute the diff against main.There's substantial implementation. Let me read the core source files.Now the orchestration in tools.py:This is a large, well-documented implementation. Let me examine the tests and compare against the `count_tools` template for the patterns being followed.Let me read the SQL and render tests, and compare with the `count_tools` template.Let me check the test fixture and the registration/config diffs.Let me check the render tests to see if the float stat formatting is deliberately asserted.Let me pin down line numbers for my findings.I have gathered full context: the issue contract, the design summary, all knowledge-base principles, the branch diff, all three source modules, and all three test modules. The diff contains substantial implementation (not just plan files), so the review proceeds.

The implementation closely follows the `count_records` template and the design summary: fail-closed `where` validation, AST-only dialect SQL, the two-tier view dispatch, the distinct row-count gate, the duplication-driven value lists, the column cap, and the `n` clamp are all present and well-tested (SQLite end-to-end + per-dialect rendered-SQL assertions). Registration, `tach.toml`, `.importlinter`, and the roadmap update are all complete and consistent.

Two substantive findings:

src/mcp_tools_sql/summarize/render.py:178 — medium — `_fmt_stat` rounds every float stat to one decimal, but this path also handles numeric `min`/`max`/`sum`, not just averages. On SQLite a `REAL`/`NUMERIC` column returns Python floats, so a price column with true min `0.01` / max `19.99` renders as `0.0` / `20.0` — a misrepresented extreme in a data-quality tool (the contract calls silently-wrong numbers the worst failure mode). T-SQL escapes this only because pyodbc returns `Decimal` (hits the `str()` branch); the divergence is untested — the fixture has no float/decimal column. Only mean/len_avg/size_avg should round; min/max/sum should render exactly.

src/mcp_tools_sql/summarize/tools.py:400 — low — the `n` clamp note is appended to the summary regardless of view, but `n` only affects deep-view value lists. A wide-table triage call with `n=999` (no value lists at all), or a deep call over only `other`/all-null columns, still gets `Requested n=999 … using 50.` appended, referencing a knob that had no effect on the output.
**Decisions**:
Verdict(decision='tasks', tasks=['Fix _fmt_stat at src/mcp_tools_sql/summarize/render.py:178 so it does not blanket-round all float stats to one decimal: render min/max/sum exactly (preserving values like 0.01 and 19.99) while rounding only the averages (mean/len_avg/size_avg); add a test with a float/decimal column (e.g. a price column with min 0.01 / max 19.99) to cover the extremes.'], escalate_reason=None)
**Changes**:
applied

## Round 3 — 2026-08-05
**Findings**:
I'll gather context. Let me start by exploring the knowledge base, pr_info, and the issue in parallel.Let me read the remaining issue content, the summary, and compute the diff.Let me check the git state and branches.There's substantial implementation. Let me read the knowledge base and the core source files.Now let me read the three core implementation files.Now the orchestration file:The implementation is substantial and thorough. Let me verify the wiring, check the tests, and run the quality checks.Wiring looks correct. Let me check prior review logs to avoid repeating findings, and run the test suite.Prior findings (clamp separator, float formatting) have been addressed. Let me run the tests and quality checks.All 125 tests pass. Let me run type/lint checks to catch any real defects, and scan the test coverage.mypy is clean and all tests pass. Let me confirm the round-2 fix (exact float min/max rendering) is actually covered by a test.I've completed a thorough round-3 review. Context gathered: all four knowledge-base principle files, issue #43 and its full contract/decisions, `pr_info/steps/summary.md` and the prior implementation review log, and the full branch diff against `origin/main` (the diff contains real implementation — the `summarize` package plus wiring — not just plan files).

Verification performed:
- Traced the full pipeline in `sql.py`, `render.py`, `tools.py` against the contract: fail-closed `where` validation, AST-only dialect SQL, `to_identifier(quoted=True)`, type categoriser ordering (LOB/rowversion guards, boolean-before-numeric), scalar-pass casts (`AVG`/`SUM` FLOAT/BIGINT, integer-only guard), `LEN`/`DATALENGTH` split, LOB exclusion from distinct/value lists, total value-list ordering, distinct 1M gate (triage-only), 50-column cap, `n` clamp, two-tier dispatch, remainder arithmetic, and the zero-row/unknown-column messages — all consistent with the design.
- Wiring (`schema_tools.py`, `server.py`, `tach.toml`, `.importlinter`) and roadmap update all correct and consistent.
- The two prior medium findings (clamp-note separator; exact float `min`/`max`/`sum` vs rounded averages) are fixed and now covered by dedicated tests.
- `mypy` clean; all 125 `tests/summarize` tests pass.

No critical or high findings. The one remaining low item (clamp note surfacing in triage / no-value-list calls) was already recorded and deliberately left in earlier rounds; from round 3 only critical/high are actionable.

NO FINDINGS
**Decisions**:
Verdict(decision='dismiss', tasks=[], escalate_reason=None)
**Changes**:
rebase-needed
**Escalate reason**: rebase
