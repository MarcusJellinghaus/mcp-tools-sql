# Implementation Review Log — Issue #9

Run 1 — 2026-05-02

## Round 1 — 2026-05-02

**Findings**:
1. (Accept) Backend resource leak in `run()` — `open_backend` not closed when `overall_ok=False`
2. (Accept) Backend not closed in `verify_connection` when `execute_query("SELECT 1")` raises
3. (Accept) Dead code: `_build_project_template_pyproject` defined but never called
4. (Accept) Help text for `--config` promises pyproject.toml discovery that isn't implemented
5. (Skip) Importing private `_has_sensitive_keys`/`_read_toml` from loader — internal modules, same package
6. (Skip) No skip-M2 summary when connection unresolvable — UX polish, CONFIG already shows errors
7. (Skip) `_pad` truncation without indicator — not currently a problem
8. (Positive) All 14 required tests (i)–(xiv) present and correct
9. (Skip) `credential_env_var` sensitive key warning — intentional per spec
10. (Skip) `extract_sql_params` regex false positives — known v1 limitation
11. (Skip) `_build_project_template_standalone` ignores backend param — intentional, `del backend` explicit

**Decisions**:
- Accept 1–4: all bounded-effort fixes, real issues
- Skip 5–7, 9–11: cosmetic, pre-existing design choices, or known limitations

**Changes**:
- `verify.py`: wrapped M2 block in try/finally to always close `open_backend`
- `verify.py`: added `backend.close()` in `verify_connection` except block (guarded)
- `init.py`: removed dead function `_build_project_template_pyproject`
- `main.py`: corrected `--config` help text to reflect actual discovery behavior

**Status**: committed (b04a471)

## Round 2 — 2026-05-02

**Findings**: None. Round 1 fixes are clean — no regressions, no new issues.

**Decisions**: N/A

**Changes**: None

**Status**: no changes needed

## Final Status

- **Rounds**: 2 (1 with code changes, 1 clean)
- **Commits**: 1 (`b04a471`)
- **Vulture**: clean
- **Lint-imports**: 2 contracts kept, 0 broken
- **All checks passing**: pylint, pytest (183 passed, 2 skipped), mypy, tach, lint-imports
