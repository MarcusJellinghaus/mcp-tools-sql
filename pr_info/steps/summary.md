# Issue #36 — CI checks + dev toolchain consolidation

## Overview

A single, small **CI-config + dependency PR**. No application code changes. Brings
this repo's CI in line with the peer group (primarily `mcp_coder`) by adding three
regression-catching checks and making `mcp-tools-py` the single source of truth for
dev-tool versions.

The "test" for every item is the CI run itself (plus local quality checks). There is
no new application logic, so classic unit-test TDD applies only weakly; each step
states its concrete verification command, which plays the role of the test.

## Scope (5 independent items → 5 commits)

| # | Item | Type |
|---|------|------|
| 1 | Consolidate dev toolchain via `mcp-tools-py` | dependency |
| 2 | `no-url-deps` script + `test` matrix entry | script + CI |
| 3 | File-size guard + `.large-files-allowlist` | config + CI |
| 4 | `pycycle` cyclic-import check in `architecture` matrix | CI |
| 5 | Broaden ruff command scope (`src` → `src tests`) | CI (no-op) |

Items are independent and low-risk. Order follows the issue's natural grouping:
dependency change first (touches the CI install set), then the cheap CI items, then
the one-line ruff broadening.

## Architectural / design changes

**None to the application architecture.** The layered module structure, import
contracts (`.importlinter` / `tach.toml`), and backends are untouched.

The changes are to the **project's quality-governance toolchain**:

- **Single source of declaration for dev tools.** `mcp-tools-py` declares `ruff`,
  `black`, `isort`, `pylint`, `mypy`, `tach`, `vulture`, `pytest*` as *runtime*
  dependencies. Adding it to `[dev]` and removing the redundant explicit pins makes
  the dev-loop tooling (the `mcp-tools-py` MCP server) and CI resolve the same tool
  declarations. `pycycle` stays explicit because `mcp-tools-py` ships it only in its
  own `[dev]` extra. This is graph-neutral: `mcp-tools-py` is already pulled
  transitively today via `mcp-coder`.
- **File-size governance.** A `mcp-coder check file-size` gate (max 750 lines) with a
  grandfather allowlist (`mcp-tools-sql.md`, 1053 lines — the only tracked file over
  the limit). Caps unbounded file growth.
- **Cyclic-import detection.** `pycycle` catches import-time cycles that tach +
  import-linter do not. Runs PR-only (in the `architecture` job).
- **URL-dependency guard.** A stdlib-only `tools/check_no_url_deps.py` fails CI if
  `[project]` deps gain a `git+` / `@ http` / `@ file` spec that would break PyPI
  installs.

## Files created / modified

**Created:**
- `tools/check_no_url_deps.py` — ported verbatim from `mcp_coder` (stdlib only).
- `.large-files-allowlist` — grandfather list for the file-size check.

**Modified:**
- `pyproject.toml` — `[project.optional-dependencies].dev` reshaped.
- `mcp-tools-sql.md` — drop the `pydeps` line from the documented `dev` block.
- `.github/workflows/ci.yml` — 3 new matrix entries + 1 broadened command string.

**Not changed:** any `src/` or `tests/` module, `.importlinter`, `tach.toml`,
integration-test jobs.

## Cross-cutting verification (run after each step)

- `mcp__tools-py__run_pylint_check`, `mcp__tools-py__run_pytest_check`
  (`extra_args=["-n","auto","-m","not sqlite_integration and not mssql_integration and not postgresql_integration"]`),
  `mcp__tools-py__run_mypy_check` — all green.
- Step 1 additionally: confirm `.[dev]` still installs and `black --check src tests`
  stays green (the one place a version delta could surface — `mcp-tools-py` floors
  `black>=26.5.1`).

## Out of scope

Test-file docstring enforcement (the `tests/**/*.py = ["D","DOC"]` ignore stays),
integration-job changes, `pylint -E` → full pylint, splitting `mcp-tools-sql.md`.
