# Plan Review Log #1 — Issue #28: Config-authoring helpers and per-entry verify

**Branch:** `28-config-authoring-helpers-and-per-entry-verify`
**Plan files reviewed:** `pr_info/steps/summary.md`, `pr_info/steps/step_1.md`..`step_4.md`
**Supervisor model:** claude-opus-4-7[1m]

---

## Round 1 — 2026-05-17

**Findings:**
- [CRITICAL] step_4: per-entry tests cannot be staged before the `verify_one_*` extraction (single-commit ordering must put extraction first).
- [CRITICAL] step_4: `verify_one_update` algorithm under-specified — the current `verify_updates` body has TWO `continue` early-returns (bad-identifier → 1 row, missing-table → 3 rows), and the `continue → return result` substitution must apply to both.
- [ACCEPT] step_3: combined-doc algorithm contradicts the static-header placement, putting `# Example UPDATE definition` above the queries block — switch to split `_build_query_block()` / `_build_update_block()` helpers preserving today's between-blocks layout.
- [ACCEPT] step_1: tests #3 and #5 had self-contradicting asides — tighten to a single clear pydantic-rejection case each.
- [ACCEPT] step_2: `_add_entry` must wrap nested `dict` payloads in `tomlkit.table()` so `[updates.<n>.key]` renders as a sub-table header, not `key = {...}` inline; add a test asserting the sub-table header.
- [ACCEPT] step_2: test #11 (parent-pruning) — add a `tomlkit.dumps` + `tomllib.loads` round-trip robustness assertion to catch tomlkit trivia retention.
- [ACCEPT] step_4: snapshot test must pass `--database-config` pointing into `tmp_path` so it does not pick up the user's real `~/.mcp-tools-sql/config.toml`.
- [ACCEPT] summary: add a one-line "no new project dependencies" note.
- [QUESTION→pre-decided] builder `**kwargs` vs. enumerated fields — issue's "Constraints & Rationale" already chose enumerated; honored without escalating.
- [QUESTION→pre-decided] eager-at-import vs. lazy template compute — issue chose eager ("computed once at module load"); honored without escalating.
- [SKIP] cosmetic: `list_configured_tools` `or {}`, `bad_table` fixture, mixed pseudocode indentation, "30+ existing verify tests" count.

**Decisions:** Accept all CRITICAL and ACCEPT findings. Skip cosmetic items. Honor the issue's pre-decided answers for the two QUESTION items.

**User decisions:** None — supervisor proceeded autonomously per skill's "default to simpler plans rather than asking" guidance; the two QUESTION items are pre-decided by issue #28 itself.

**Changes:** Applied via `/plan_update` engineer subagent:
- `pr_info/steps/step_1.md` — tightened tests #3 and #5 to single clear pydantic-rejection cases.
- `pr_info/steps/step_2.md` — `_add_entry` algorithm now wraps nested dicts in `tomlkit.table()`; added test #7a (sub-table header assertion); extended test #11 with `dumps`+`loads` round-trip check.
- `pr_info/steps/step_3.md` — replaced combined-doc algorithm with split `_build_query_block()` / `_build_update_block()` helpers; final assembly interleaves header → query block → middle UPDATE header → update block → footer; removed the speculative branch.
- `pr_info/steps/step_4.md` — rewrote algorithm with explicit 4-substep sequence (snapshot first → extract → per-entry tests → re-verify snapshot); enumerated both `continue → return result` substitutions in `verify_one_update`; added the `--database-config` wiring note.
- `pr_info/steps/summary.md` — added "no new project dependencies" note under "Files NOT changed".

**Status:** Changes ready to commit. Commit message: `docs(plan): apply round 1 review fixes to issue #28 plan`

## Round 2 — 2026-05-17

**Findings:**
- [CRITICAL] step_2: `_add_entry` key-emission order bug. Pydantic emits fields in declaration order (`description, sql, params, max_rows_default, ...`), so iterating `payload.items()` writes the `[queries.<n>.params.<key>]` sub-table BEFORE the scalar `max_rows_default = 1` — and TOML semantics then re-parent that scalar under `params.<key>`. Round-trip test would fail.
- [CRITICAL] step_3: same root cause silently corrupts the generated `_PROJECT_TEMPLATE_STANDALONE` — the marker-presence test does not catch it. Need a parse-and-uncomment guard that strips `# ` and asserts semantic equalities on the parsed result.
- [QUESTION→honored issue] snapshot test sqlite error-message drift — engineer floated dropping the snapshot in favor of equality tests only. Issue #28's "Tests" and "Acceptance criteria" mandate the snapshot, so kept as-is. Not escalated.
- [SKIP] cosmetic: `# `-with-trailing-space ambiguity in step_3 (chosen variant is exercised by the marker test); `description=""` lean-output already handled by `exclude_defaults=True`; step_1 test #2 silent-override is per issue Decision #2.

**Decisions:** Accept both CRITICAL fixes. Skip cosmetic items. Honor the issue on the snapshot QUESTION.

**User decisions:** None — both CRITICAL fixes are mechanical; the QUESTION is pre-decided by the issue's acceptance criteria.

**Changes:** Applied via `/plan_update` engineer subagent:
- `pr_info/steps/step_2.md` — rewrote `_add_entry` from single-pass to three-pass (scalars → dict sub-tables → list AoTs); added rationale paragraph and test #1a asserting `max_rows_default` line precedes the `[queries.<n>.params.id]` header in the rendered output.
- `pr_info/steps/step_3.md` — added parse-and-uncomment test (strip `# `, parse via `tomllib.loads`, assert four semantic equalities on the result) with rationale paragraph.

**Status:** Changes ready to commit. Commit message: `docs(plan): apply round 2 review fixes to issue #28 plan`

## Round 3 — 2026-05-17

**Findings:**
- [ACCEPT] step_2: `_add_entry` pass 2 doesn't make recursive dict wrapping explicit. `params = {"id": {...}}` post-`model_dump` is `dict[str, dict]`; without recursive `tomlkit.table()` wrapping the inner dicts render as inline tables (`params.id = {...}`) instead of the required `[queries.<n>.params.id]` sub-table headers.
- [ACCEPT-minor] step_3: import-time computation of `_PROJECT_TEMPLATE_STANDALONE` means a future pydantic `ValidationError` from `build_*` would make `mcp_tools_sql.cli.commands.init` unimportable and break every CLI command. Acceptable trade-off but worth one-line documentation.
- [SKIP] step_2: AoT-element recursion not needed today (`UpdateFieldConfig` is flat) — engineer accepted the existing scoping note.
- [SKIP] step_2 test 11: `"queries" not in doc` plus round-trip reparse already covers tomlkit semantics — no change.
- [SKIP] step_3: minor byte-content differences between today's static template and helper-generated template are parse-equivalent; existing `test_init_generates_valid_toml` passes regardless.
- [QUESTION→no fix] step_4 snapshot path-scrubbing — snapshot is correctly scoped to QUESTIONS/UPDATES sections which don't echo the db path; no fix needed.
- [QUESTION→no fix] step_4 bad-identifier fixture (`table = "drop;"`) loads fine and trips `IDENTIFIER_PATTERN` at verify time as intended.

**Decisions:** Accept both substantive ACCEPTs. Skip cosmetic items.

**User decisions:** None — both fixes are mechanical doc tightenings.

**Changes:** Applied via `/plan_update` engineer subagent:
- `pr_info/steps/step_2.md` — pass 2 pseudocode now uses recursive `_to_toml_table` helper; added concrete `QueryConfig.params` walkthrough showing why recursion is required; pass 3 commented to note flat AoT shape today.
- `pr_info/steps/step_3.md` — added one-bullet note on the import-time failure mode and its acceptable trade-off.

**Status:** Changes ready to commit. Commit message: `docs(plan): apply round 3 review fixes to issue #28 plan`. Round 3 engineer rated the plan "ready for approval" with this as the only substantive change.

## Round 4 — 2026-05-17

**Findings:**
- Multiple [ACCEPT] items, all of them affirmations of in-plan guards (three-pass scalar/sub-table/AoT emission, snapshot-first work sequence in step_4, both `continue → return result` substitutions enumerated, `_remove_entry` round-trip reparse defense, import-time risk documented, lean-output rule for `max_rows_hard`). No fixes required — these are praise items, not change requests.
- [QUESTION→no fix] step_1: `name` kwarg is unused inside the builders → pylint `unused-argument`. Implementer-in-flight resolution (use it in a ValidationError wrap, `del name`, or `# pylint: disable=unused-argument`). Not a planning-level concern.
- [QUESTION→no fix] step_1: `description: str = ""` precedes required keyword-only `sql: str` — legal because of `*` separator. Implementer detail.
- [SKIP] step_4 `_extract_section` described in prose, not code — LLM implementer can write it from the spec.
- [SKIP] step_3 `f"# {line}"` vs `"#"` blank-line choice — both round-trip; implementer picks.
- [SKIP] step_2 test 7a `"key = {" not in dumped` — theoretical false-positive scenarios are not realistic.

**Decisions:** No changes accepted — round 4 found zero substantive issues.

**User decisions:** None.

**Changes:** None — plan files untouched this round.

**Status:** Converged. No commit produced.

---

## Final Status

**Plan ready for approval.**

- **Rounds run:** 4
- **Commits produced (plan content):** 3
  - `bbe9ecc` — `docs(plan): apply round 1 review fixes to issue #28 plan` (5 files)
  - `93198e5` — `docs(plan): apply round 2 review fixes to issue #28 plan` (2 files)
  - `3031395` — `docs(plan): apply round 3 review fixes to issue #28 plan` (2 files)
- **Convergence:** Round 4 produced zero plan changes; engineer rated the plan "ready for approval" outright.
- **Review log commit:** This log committed as a follow-up after Final Status.

**What materially changed across the four rounds:**

1. **Round 1 — broad cleanup.** Tightened test #3/#5 descriptions in step_1; introduced `tomlkit.table()` wrapping for nested dicts in step_2; resolved step_3's combined-doc vs split-block ambiguity in favor of `_build_query_block()` / `_build_update_block()` preserving today's between-blocks layout; reordered step_4 work sequence and enumerated both `verify_one_update` early-returns; added "no new dependencies" note to summary.
2. **Round 2 — TOML scalar/sub-table ordering bug.** Rewrote step_2's `_add_entry` from single-pass to three-pass (scalars → dict sub-tables → list AoTs) to prevent TOML re-parenting scalars under sub-table headers; added test #1a and a parse-and-uncomment semantic guard in step_3 to catch the same class of bug at the init layer.
3. **Round 3 — nested-dict recursion.** Made recursive `tomlkit.table()` wrapping explicit in step_2's pass 2 (via a `_to_toml_table` helper); documented the import-time `ValidationError` failure mode for step_3's eager template computation as an accepted trade-off.
4. **Round 4 — convergence.** No changes; plan approved by an independent reviewer.

**Open implementer-in-flight nits** (not planning issues):
- `name` kwarg in `build_*` is currently unused — resolve with one of: ValidationError-wrap usage, `del name`, or `# pylint: disable=unused-argument`.
- `_extract_section` helper is described in prose; implementer writes from spec.
- `# `-with-trailing-space vs `#` blank-line choice in the generated commented template — both valid; implementer picks based on ruff/black preference.

**Recommendation for next step:** run `/plan_approve` (or the appropriate gating skill) to promote the issue past `status-03f:planning-failed`.
