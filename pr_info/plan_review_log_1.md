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

## Round 3 — 2026-05-07
**Findings**:
- S18: Step 2 WHERE missed two test files that reference the renamed `max_rows` field (`tests/test_smoke.py`, `tests/config/test_loader.py`). Without explicit updates, pytest would fail at the end of Step 2.

**Decisions**:
- S18: ACCEPT (mechanical correctness — required for pytest to pass after the rename).

**User decisions**: None.

**Changes**:
- step_2.md: added `tests/test_smoke.py` (`qc.max_rows == 100` → `qc.max_rows_default == 100`) and `tests/config/test_loader.py` (TOML `max_rows = 50` → `max_rows_default = 50`; assertion `.max_rows == 50` → `.max_rows_default == 50`) to WHERE.

**Status**: Pending commit.

## Round 4 — 2026-05-07
**Findings**:
- S19: verify.py result-dict keys, error text, and docstring needed an explicit policy after the `max_rows` field rename. (DESIGN/REQUIREMENTS)
- S20: TOML literal at `tests/cli/test_verify.py:937` not enumerated in Step 2 WHERE.
- S21: `tests/cli/test_verify.py` had 7 `QueryConfig(..., max_rows=N)` call sites + 4 result-key/error-text assertion sites + a test-method name not enumerated.
- S22: `tests/test_default_queries.py` test methods `test_read_columns_has_filter_param` / `test_read_columns_has_max_rows_param` need explicit handling — both fully obsolete after Step 4.

**Decisions**:
- S19: ACCEPT option A — rename verify.py keys/error/docstring in lockstep with the field. (User decision)
- S20: SKIP — keep generic "adjust field references" wording for the TOML literal. (User decision)
- S21: ACCEPT option A — enumerate the call sites, assertion sites, and test-method rename. (User decision)
- S22: ACCEPT option A — delete both obsolete test methods entirely. (User decision)

**User decisions**:
- S19 (verify.py result-key policy): A — rename in lockstep.
- S20 (TOML literal enumeration): B — keep generic.
- S21 (test_verify.py call-site enumeration): A — enumerate.
- S22 (test_default_queries.py obsolete methods): A — delete both.

**Changes**:
- step_2.md: added explicit WHERE/HOW entries for `verify.py` (result-key, error text, docstring lines 524/528, field access); replaced generic `tests/cli/test_verify.py` entry with explicit enumeration of 7 `QueryConfig` keyword call sites, result-key assertions, error-text assertions, and rename of `test_verify_queries_detects_missing_max_rows` → `..._max_rows_default`. Generic wording retained for the line 937 TOML literal per user choice.
- step_4.md: replaced generic wording for `tests/test_default_queries.py` with explicit deletion instruction for `test_read_columns_has_filter_param` and `test_read_columns_has_max_rows_param`, with rationale that their coverage is provided elsewhere (Step 2 + Step 6).

**Status**: Pending commit.

## Round 5 — 2026-05-07
**Findings**:
- S23: `src/mcp_tools_sql/cli/commands/init.py` line 24 has `# max_rows = 1` in the user-facing `_PROJECT_TEMPLATE_STANDALONE` TOML template. Uncommenting it after the rename would fail Pydantic validation.
- S24: `docs/cli.md` lines 152 and 205 reference `max_rows` (line 205 shows the verify output `read_schemas.max_rows         100` which becomes `read_schemas.max_rows_default` after the S19 rename).

**Decisions**:
- S23: ACCEPT (mechanical fix; user-facing template breakage). (Supervisor auto-accept.)
- S24: ACCEPT option A — update docs/cli.md in this PR alongside the verify output change. (User decision.)

**User decisions**:
- S24 (docs/cli.md scope): A — include in this PR.

**Changes**:
- step_2.md: added `src/mcp_tools_sql/cli/commands/init.py` (line 24: `# max_rows = 1` → `# max_rows_default = 1`) and `docs/cli.md` (line 152 and line 205) to WHERE.
- summary.md: added `src/mcp_tools_sql/cli/commands/init.py` and `docs/cli.md` to the Files Modified listing.

**Status**: Pending commit.

## Round 6 — 2026-05-07
**Findings**:
- S25: `mcp-tools-sql.md` (root planning doc, linked from README) has ~10 stale `max_rows` references in TOML examples, prose, and a future-API mockup. Doc is marked "Status: Draft / Brainstorm" but is user-discoverable.

**Decisions**:
- S25: ACCEPT option A — include the doc in Step 2's WHERE for consistency with S24 (docs/cli.md). (User decision.)

**User decisions**:
- S25 (mcp-tools-sql.md scope): A — include in this PR.

**Changes**:
- step_2.md: added `mcp-tools-sql.md` (root) to WHERE — global `max_rows` → `max_rows_default` rename across TOML examples, prose, verify-output mockups, and the `add_query(...)` future-API signature line.
- summary.md: added `mcp-tools-sql.md` to the Files Modified table.

**Status**: Pending commit.

## Final Status

**Plan ready for implementation.**

- Rounds run: 7 (Rounds 1-6 produced changes; Round 7 produced zero changes, terminating the loop).
- Findings addressed: 25 (S1-S25). All STRAIGHTFORWARD findings auto-accepted; design/scope questions (S19, S24, S25) escalated to user for decisions.
- User decisions:
  - S19 (verify.py result-key policy): A — rename in lockstep.
  - S20 (TOML literal enumeration in test_verify.py): B — keep generic wording.
  - S21 (test_verify.py call-site enumeration): A — enumerate explicitly.
  - S22 (obsolete test methods in test_default_queries.py): A — delete both.
  - S24 (docs/cli.md scope): A — include in this PR.
  - S25 (mcp-tools-sql.md brainstorm doc scope): A — include in this PR.
- Commits produced (6, on branch `5-dynamic-select-tool-registration`):
  - Round 1: b582dcc
  - Round 2: 0c971d2
  - Round 3: 84fd2ff
  - Round 4: 680d429
  - Round 5: 4c06466
  - Round 6: 19f4f1d
- Plan files final state: `pr_info/steps/summary.md` + step_1.md through step_6.md.
- Coverage verified: all `max_rows` and `filter` references across source, tests, docs, and the brainstorm doc are either enumerated in a step's WHERE list or intentionally preserved (e.g., MCP tool kwargs that keep their public name).

The plan is mechanically complete and ready for the implementation phase.
