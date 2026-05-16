# Implementation Review Log — Run 1

**Issue:** #8 — Query validation tool (`validate_sql`)
**Branch:** `8-query-validation-tool-validate-sql`
**Started:** 2026-05-16

Rounds of code review + fix performed by a supervisor (me) delegating to engineer subagents.
Each round is appended below.

---

## Round 1 — 2026-05-16

**Findings** (from `/implementation_review`):
1. `validation_tools.py:150` — duplicated f-string in error message (cosmetic copy-paste).
2. `validation_tools.py:114` — `SET SHOWPLAN_TEXT OFF` in `finally` could mask inner exception.
3. `validation_tools.py:39` em-dash in `_DESCRIPTION` (suspected mojibake — confirmed clean).
4. `server.py:21` imports module-private `_PROGRAMMATIC_BUILTIN_TOOLS` from `schema_tools`.
5. `backends/base.py:50-58` abstract return type vs `@contextmanager` distinction.
6. `validation_tools.py:140` broad `except Exception` (intentional per Decision #8).
7. `test_validation_tools.py:173` — no mocked sad-path test for `_explain` pyodbc errors.
8. `validation_tools.py:25` — `_INVALID_SQL_EXC` broadly typed (correct, handles empty pyodbc tuple).
9. `tests/test_validation_tools.py` — repetitive setup across pre-flight tests (~150 lines DRY savings possible).
10. Tests import `_explain` + `MSSQLTestEnv` (accepted test-only pattern).

**Decisions**:
- **Accept #1** — trivial cosmetic, Boy Scout fix.
- **Accept #4** — rename `_PROGRAMMATIC_BUILTIN_TOOLS` → `PROGRAMMATIC_BUILTIN_TOOLS`; cross-module use of `_`-prefixed name violates Python convention; small intent-clarifying rename.
- **Skip #2** — matches existing `MSSQLBackend.explain()` pattern; isolated connection bounds damage; consistency over speculative corner case.
- **Skip #3** — confirmed clean source, diff-rendering artifact only.
- **Skip #5, #6, #8, #10** — correct as designed.
- **Skip #7** — integration tests cover the contract; "test behaviour, not implementation".
- **Skip #9** — YAGNI ("if more rules are added"); 583 lines is under the 600-line guideline; refactor risk + explicit-test readability outweigh DRY savings.

**Changes**:
- `src/mcp_tools_sql/validation_tools.py` — collapsed two adjacent f-strings (RuntimeError bucket) into one; other buckets already single f-strings.
- `src/mcp_tools_sql/schema_tools.py` — renamed `_PROGRAMMATIC_BUILTIN_TOOLS` → `PROGRAMMATIC_BUILTIN_TOOLS` (definition + docstring).
- `src/mcp_tools_sql/server.py` — updated import + usage.
- `tests/test_server.py` — updated import + usage.

**Quality gate**: format ✓, pylint ✓, pytest ✓ (398 passed, 16 skipped), mypy ✓.

**Status**: committed as `6bbf0e8` and pushed.

## Round 2 — 2026-05-16

**Findings**: none.

Round-1 fixes verified clean: f-string collapse intact, rename applied at definition + all 5 call sites with no stragglers. Re-run quality gates green (pytest 398/16, pylint, mypy, ruff). Pre-existing oversized files flagged by `check_file_size` are all out of scope for this branch.

**Decisions**: nothing to triage.

**Changes**: none.

**Status**: zero-change round — loop exit condition met.

## Post-loop checks

- **`run_lint_imports_check`**: PASSED (2 contracts kept, 0 broken). No architecture violations.
- **`run_vulture_check`** (60% confidence): 4 false positives — `__enter__` / `__exit__` on `MagicMock` context managers in `tests/test_validation_tools.py` (lines 181-182, 216-217). Vulture's blind spot for the `with` protocol on mocks. Added a new whitelist section in `vulture_whitelist.py`:

  ```
  # Context-manager protocol on test mocks (invoked by `with` statements)
  _.__enter__
  _.__exit__
  ```

  Re-run: 0 issues. Committed as `1a06cc0`.

## Final Status

- **Rounds run**: 2 (Round 1: 2 accepted fixes, 8 skipped; Round 2: zero-change clean round).
- **Commits produced by this review**:
  - `6bbf0e8` — refactor(schema_tools): make PROGRAMMATIC_BUILTIN_TOOLS public and collapse duplicated f-string
  - `1a06cc0` — chore(vulture): whitelist context-manager dunders on test mocks
- **Quality gates at exit**: pylint ✓, pytest ✓ (398 passed, 16 skipped), mypy ✓, ruff ✓, vulture ✓, lint-imports ✓.
- **Outcome**: code review complete; no remaining issues. Branch is merge-ready pending CI confirmation and PR creation.
