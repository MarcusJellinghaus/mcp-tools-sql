# review-implementation review log 2

Issue #63 — `max_rows=-1` bypasses the row cap.
Continues from `implementation_review_log_1.md` (3 rounds, ended on a rebase handoff).

## Round 1 — 2026-09-28

**Findings**: NO FINDINGS.

The reviewer re-verified the items most at risk of regressing across the rebase,
and each holds:

- `MAX_ROWS_MIN` (`formatting.py:13`) is the single shared bound; no bare `1`
  literals remain at the four former sites.
- Both runtime fallbacks (`query_helpers.py:204`, `:358`) route through
  `_default_max_rows`, so an omitted `max_rows` emits no below-minimum note.
- Every slice site is floored. The two `format_rows` callers that skip
  `_cap_max_rows` pass non-caller-supplied values (`len(rows)`, `COLUMN_CAP`).
- Layered-architecture dependency `query_helpers` → `formatting` is downward and
  allowed.

Noted but out of scope: a stale "max_rows_default set" mention in
`mcp-tools-sql.md:780`, a draft brainstorm document, not maintained
documentation.

**Decisions**: nothing to accept — no findings raised.

**Changes**: none.

**Status**: no changes needed.

## Final Status

Review complete after one round with zero findings and zero code changes.

- `run_vulture_check` — clean, no output.
- `run_lint_imports_check` — PASSED, 2 contracts kept, 0 broken.
- Branch tests: 103 affected tests pass locally; branch CI reports PASSED.
- All 12 implementation tasks complete; branch up to date with `main`.
