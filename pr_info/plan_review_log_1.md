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

## Round 2 — 2026-05-07
**Findings**:
- S15: Step 3 missed adding `tool_builder` to `cli.commands` `depends_on` in `tach.toml` — would fail tach check.
- S16: Step 4 had loose wording for the affected `test_verify_queries_accepts_filter_and_max_rows_as_non_sql_params` test — should be explicit (rename + invert).
- S17: Step 2 didn't pre-declare the mypy handling for `max_rows_hard: int | None` at clamp call sites — implementer would have to invent it.

**Decisions**:
- S15, S16, S17: ACCEPT (all straightforward correctness/clarity improvements).

**User decisions**: None — no design/requirements questions raised this round.

**Changes**:
- step_2.md: added HOW note for mypy handling of `max_rows_hard: int | None` (cast or assert pattern at clamp call sites; same pattern used after Step 3 moves the function).
- step_3.md: added `{ path = "mcp_tools_sql.tool_builder" }` to the `cli.commands` module's `depends_on` in the `tach.toml` change list.
- step_4.md: replaced loose "any tests..." wording with explicit rename/invert of `test_verify_queries_accepts_filter_and_max_rows_as_non_sql_params` to `..._rejects_...`, asserting `ok is False` and error contains `"not used in SQL"`.

**Status**: Pending commit.
