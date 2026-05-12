# Implementation Review Log — Run 1

**Branch**: `5-dynamic-select-tool-registration`
**Issue**: #5 — Dynamic SELECT tool registration
**Started**: 2026-05-12

This log records each round of the supervised implementation review:
findings from `/implementation_review`, accept/skip triage decisions,
changes implemented, and the round outcome.

## Round 1 — 2026-05-12

**Findings (review subagent):**
- Cosmetic: stale class name `QueryToolRegistry` in commit message `4f467d5` (actual class is `QueryTools`).
- Cosmetic: `apply_filter` exported without underscore — engineer confirmed this matches spec intent.
- Accept: `max_rows_hard: int | None` requires `cast(int, ...)` in `tool_builder.py:67` after the `model_validator` resolves it.
- Cosmetic: `_tool_fn` mutates `kwargs` via `.pop()` — works because FastMCP passes a fresh dict.
- Cosmetic: `stripped or None` passed to `backend.execute_query` when no params resolved.
- **Accept: `max_rows=null` from MCP client → `TypeError` on `requested > hard` clamp comparison** (implicit `max_rows` was typed `Optional[int]`).
- Cosmetic: `default_queries.toml` reloaded on every `SchemaTools.register()` call.
- Cosmetic: `_NAME_RE` and `_TRUNCATION_HINT` are class attrs vs module constants.
- Cosmetic: `test_missing_required_param_errors` uses `isError`-asserting pattern inconsistent with surrounding suite (still correct).

**Spec coverage:** all 19 issue-#5 decisions implemented; all required tests present.

**Check baseline (before fix):** pylint, pytest (236 passed / 2 skipped), mypy, ruff, bandit — all PASS.

**Decisions:**
- **Accepted #6 (`max_rows=null`)** — real protocol edge case, tiny fix. Engineer changed `Annotated[Optional[int], ...]` → `Annotated[int, ...]` for the implicit `max_rows` parameter in `tool_builder.py`. FastMCP/Pydantic now rejects `null` at the protocol layer; semantically `max_rows` always has a default.
- **Skipped 1, 2, 4, 5, 7, 8, 9** — cosmetic / speculative / pre-existing per `software_engineering_principles.md` ("If a change only matters when someone makes a future mistake, it's speculative — skip it.")
- **Skipped #3** (`cast(int, ...)`) — refactor to computed property has no clear benefit; cast is acceptable.

**Changes:**
- `src/mcp_tools_sql/tool_builder.py` — implicit `max_rows` annotation tightened from `Optional[int]` to `int`; existing tests cover the default-when-omitted path.

**Checks after fix:** pylint, pytest (236 passed / 2 skipped), mypy, ruff — all PASS.

**Status:** committed at `44d5b85`.

## Round 2 — 2026-05-12

**Findings:** None — implementation is clean.

**Verification:**
- Round-1 fix confirmed in `tool_builder.py`: implicit `max_rows` now uses `Annotated[int, Field(...)]`; FastMCP/Pydantic rejects `null` at the protocol layer.
- pylint, pytest (236 passed / 2 skipped), mypy, ruff — all PASS.
- No regressions; no new findings.

**Status:** zero code changes — review loop terminates.

## Final Checks (vulture + lint-imports)

- `lint-imports`: PASS (2 contracts kept, 0 broken; new `tool_builder` layer recognized).
- `vulture`: initially flagged `src/mcp_tools_sql/config/models.py:51 _default_max_rows_hard` (false positive — it's a Pydantic `@model_validator(mode="after")` invoked by the framework). Added `_._default_max_rows_hard` to `vulture_whitelist.py` under a new "Pydantic @model_validator methods" section. Vulture re-run: clean.

## Final Status

**Rounds run:** 2 (round 1 produced one fix; round 2 was clean).

**Commits this review produced:**
- `44d5b85` — fix(tool_builder): type implicit max_rows as int, not Optional[int]
- (whitelist + log commits added below)

**All checks passing:** pylint, pytest (236 passed / 2 skipped), mypy, ruff, bandit, vulture, lint-imports.

**Spec coverage:** complete — all 19 issue-#5 decisions implemented; all required tests present.

**Outstanding issues:** none. Implementation is ready for PR-level review.
