# Implementation Review Log 1

Branch: 6-dynamic-update-tool-registration
Issue: #6
Date started: 2026-05-12


## Round 1 — 2026-05-12

**Findings**:
- **Critical**: `src/mcp_tools_sql/schema_tools.py:10` imports `_build_query_body`, `_build_query_sig_params` from `mcp_tools_sql.query_tools`. Both modules sit on the same layer in `.importlinter` (Layered Architecture) and `tach.toml` (`tool_implementation`). `lint-imports` reports `BROKEN: Layered Architecture`; `tach check` reports two `UndeclaredDependency` errors.
- **Accept**: `src/mcp_tools_sql/cli/commands/verify.py:32` imports `extract_sql_params` from `query_tools` but `tach.toml`'s `cli.commands` module does not declare that dependency.
- **Skip**: `formatting.format_columns` NotImplementedError stub (pre-existing); `verify._VALID_PARAM_TYPES` missing `"bool"` (pre-existing); cosmetic uses of `f"...".lstrip(".")` and implicit string concat in `update_tools.py:107`; `bandit` JSON parse error (tooling, not finding); `pr_info/` files (out of scope per knowledge base); pre-existing missing `tach.toml` entry for `mcp_tools_sql.identifiers` (tach passes — speculative).

**Decisions**:
- Critical layering violation escalated to user. User chose: extract shared helpers to a new lower-layer sibling module.
- Accept finding bundled with the critical fix (same root cause: shared helpers should live one layer down).
- Skip items recorded; not actioned.

**Changes**:
- New module `src/mcp_tools_sql/query_helpers.py` containing `extract_sql_params`, `apply_filter`, `build_query_sig_params` (promoted from `_build_query_sig_params`), `build_query_body` (promoted from `_build_query_body`).
- Updated callers: `query_tools.py`, `schema_tools.py`, `cli/commands/verify.py`, `tests/test_schema_tools.py`, `tests/test_tool_builder.py`.
- `.importlinter`: added `mcp_tools_sql.query_helpers` as its own layer beneath the tool implementations; added to `forbidden-imports` for `utils`.
- `tach.toml`: added `[[modules]]` entry for `mcp_tools_sql.query_helpers` (layer `tool_implementation`); added it to `depends_on` lists of `schema_tools`, `query_tools`, `cli.commands`.
- Quality checks all pass: pylint, mypy, pytest (282 passed / 2 skipped), lint-imports, tach.

**Status**: Code changes complete; ready to commit.


## Round 2 — 2026-05-12

**Findings**:
- **Critical**: none.
- **Accept**: none. Round 1's refactor landed cleanly: `query_helpers.py` documented, callers symmetric, no stale helpers left in `query_tools.py`, tests relocated and re-imported correctly.
- **Skip**: `identifiers.py` not listed in `tach.toml`/`.importlinter` (speculative — both linters pass today); cross-module `_UNSET` underscore import (intentional sentinel contract, tested); two consecutive `cfg.fields` loops in `update_tools.py:155-163` (cosmetic split for readability); `cli/commands/verify.py` size 912 lines (pre-existing oversize); test files `test_verify.py` (1112) and `test_update_tools.py` (718) exceed 600-line guideline (test files, future split).

**Decisions**:
- No findings accepted. Loop exit signal.

**Changes**:
- None.

**Status**: No code changes needed. Branch ready for finalization.


## Final Status

- Rounds run: 2 (Round 1 produced 1 commit; Round 2 produced no changes — loop exit).
- Round 1 commit: `500b9a0` — Extract shared query helpers into query_helpers module.
- Final supervisor checks:
  - `run_vulture_check`: PASS (no output)
  - `run_lint_imports_check`: PASS (2 contracts kept, 0 broken)
- All standard quality gates (pylint, pytest, mypy, ruff, lint-imports, tach, vulture) PASS on the final state of the branch.
- Branch ready for PR / merge after `check_branch_status`.
