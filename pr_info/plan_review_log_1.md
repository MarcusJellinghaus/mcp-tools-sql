# Plan Review Log — Issue #5

## Round 1 — 2026-05-07
**Findings**:
- S1: Step 3 was leaving re-export shims in `schema_tools.py` — violates "no legacy artifacts" rule.
- S2: Step 2 adds clamp inside `_build_tool_fn` then Step 3 moves the function — flagged for clarity.
- S4: Step 4 said "drop or trim" `_LEGITIMATE_NON_SQL_PARAMS` — should be full removal.
- S5: Step 4 WHERE missing `tests/cli/test_verify.py`.
- S10: Step 6 test list missing datetime parameter binding (called out in issue #5).
- S11: Step 2 missing test for combined clamp + truncation notes.
- S12: Step 2 missing `model_validator` and `Self` import notes.
- S3, S6, S7, S8, S9, S13, S14: confirmed clean / no fix needed.

**Decisions**:
- S1, S4, S5, S10, S11, S12: ACCEPT (straightforward improvements, supervisor approved).
- S2: ACCEPT only the clarifying note (do not reorder steps — borderline aesthetic, not correctness).
- S3, S6, S7, S8, S9, S13, S14: SKIP (no change needed).

**User decisions**: None — no design/requirements questions raised this round.

**Changes**:
- step_2.md: added `model_validator` + `Self` import notes; added `test_clamp_and_truncation_both_appear` test; added clarifying note that the clamp moves untouched in Step 3.
- step_3.md: removed re-export shim language; clarified `schema_tools.py` post-step contents; added `tests/test_schema_tools.py` to WHERE.
- step_4.md: hard-remove `_LEGITIMATE_NON_SQL_PARAMS` (was "drop or trim"); added behavior note for stricter param validation; added `tests/cli/test_verify.py` to WHERE.
- step_6.md: added datetime parameter binding test (`test_query_tool_binds_datetime_param`) to TDD list.

**Status**: Pending commit.
