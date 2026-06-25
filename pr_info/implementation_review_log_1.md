# Implementation Review Log — Issue #36

CI checks + dev toolchain consolidation. Small CI-config + dependency PR (no
application code changes). Supervised implementation review.

Scope reminder (from issue/Decisions):
- 5 items: dev-toolchain via `mcp-tools-py`, no-url-deps script, file-size guard +
  allowlist, pycycle matrix entry, broaden ruff scope to `src tests`.
- Tests stay exempt from ruff D/DOC. `.large-files-allowlist` must be non-empty
  (`mcp-tools-sql.md`). File-size is a `test` matrix entry, not a separate job.
  `tools/check_no_url_deps.py` ported verbatim.

## Round 1 — 2026-06-25

**Findings** (from engineer running `/implementation_review` against `main`):
- Implementation diff exists (not just docs): `.github/workflows/ci.yml`, `.large-files-allowlist` (new), `mcp-tools-sql.md`, `pyproject.toml`, `tools/check_no_url_deps.py` (new). Remaining changed files are `pr_info/**` docs.
- Critical: none.
- Confirmed-correct: `dev` extra reshaped to the 4 target entries; redundant pins + `pydeps` dropped; `pycycle>=0.0.8` kept. `check_no_url_deps.py` ported verbatim (stdlib `tomllib`, flags `git+`/`@ http`/`@ file`), exits 0. `.large-files-allowlist` non-empty (header + `mcp-tools-sql.md`). `tests/**/*.py = ["D","DOC"]` ruff ignore preserved → `ruff check src tests` is a true no-op. `no-url-deps`/`file-size` in the `test` job, `pycycle` in the PR-only `architecture` job; YAML well-formed; `--ignore` list verbatim. Only the `pydeps` doc line removed from `mcp-tools-sql.md` (no scope creep).
- Skip (non-blocking): `--max-lines 750` differs from the MCP tool's 600 default — intentional, matches the issue spec + allowlist header. `@ file`/`@ http` substring edge case left as-is — verbatim port mandated. No unit tests for the CI helper — acceptable (outside test/mypy path).

**Decisions**: All findings either confirmations (no action) or correctly-skipped non-blocking observations. No code changes warranted — implementation meets all 5 issue #36 requirements.

**Changes**: None.

**Status**: No changes needed.

## Final Status

- Rounds run: 1. Code changes made by review: none (implementation was already correct against all 5 requirements).
- Quality checks: pylint PASS, mypy `--strict src tests` PASS, pytest PASS (493 passed, 1 skipped; integration excluded), black/isort `--check` PASS.
- Supervisor-run gates: vulture — clean (no output); lint-imports — PASSED (2 contracts kept, 0 broken).
- Remote CI on branch: PASSED.
- Verdict: ready to merge. No critical or accepted findings; no follow-up work.
