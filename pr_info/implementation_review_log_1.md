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
