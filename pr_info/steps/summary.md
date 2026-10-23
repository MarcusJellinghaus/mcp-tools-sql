# Summary — Dependency hygiene (deptry) and coverage reporting (#82)

Part of MarcusJellinghaus/mcp_coder#1163. Mirrors mcp_coder#1176 (deptry) and
mcp_coder#1178 (coverage). mcp_coder's `pyproject.toml`, `ci.yml`, `tools/` and
`tests/tools/` are the blueprint, except where the issue's **Decisions** table
says otherwise.

## Goal

1. `deptry src` is clean locally and in CI, with no module-name warnings.
2. CI reports coverage (total + per-package, plus diff-coverage on PRs) in the
   step summary. Coverage is **reporting only — never a gate**.

## Architectural / design changes

### Dependency declarations
- `structlog` and `python-json-logger` leave `[project].dependencies`. Nothing in
  `src/` or `tests/` imports them; they arrive transitively via `mcp-coder-utils`
  (the local-shim rule means `src/` must never import them directly).
- `deptry` checks `src/` only. The `dev` extra is declared as a dev group
  (`optional_dependencies_dev_groups = ["dev"]`) instead of a hardcoded DEP002
  ignore list, so a `dev`-only package imported from `src/` still fails (DEP004).
- `package_module_name_map` names `pyodbc` / `psycopg` explicitly, because the
  `architecture` CI job installs `.[dev]` only and those backends are absent.

### CI topology (`.github/workflows/ci.yml`)
Before:
```
test (matrix: black, isort, pylint, ruff, pytest, mypy, no-url-deps, file-size)
sqlite-integration | postgresql-integration | mssql-integration (continue-on-error)
architecture (PR only, matrix: import-linter, tach, vulture, pycycle)
```
After:
```
test (matrix: black, isort, pylint, ruff, mypy, no-url-deps, file-size)   # pytest removed
unit-tests              --cov → .coverage.unit        → artifact coverage-data-unit
sqlite-integration      --cov → .coverage.sqlite      → artifact coverage-data-sqlite
postgresql-integration  --cov → .coverage.postgresql  → artifact coverage-data-postgresql
mssql-integration       --cov → .coverage.mssql       → artifact coverage-data-mssql
coverage  needs: the 4 above; if: always() && (PR || main)
          download coverage-data-* → combine → xml → diff-cover (PR) → step summary
architecture (PR only, matrix: + deptry)
```
- One `COVERAGE_FILE` per job, so `merge-multiple` never overwrites one job's data
  with another's. Dot-files need `include-hidden-files: true`.
- Never a gate: uploads use `if: always()`; the `coverage` job runs with
  `always()`; its download step is `continue-on-error`; a single guard writes a
  notice and exits 0 when there is no data; `diff-cover` uses `|| true`.
- Missing integration data is legitimate (exit-5 "no tests" handling, MSSQL
  `continue-on-error`, no `postgresql_integration` tests yet) →
  `if-no-files-found: ignore`. A missing unit file means breakage → default `warn`.
- The `coverage` job is a single bash step (guard → diff-cover → summary). This
  is a deliberate deviation from mcp_coder's multi-step job: the early `exit 0`
  guard would otherwise need repeated conditions on later steps.

### New tool script
`tools/ci_coverage_summary.py` — standalone, stdlib-only. It parses Cobertura
`coverage.xml`, groups line counts by top-level package (the root `"."` becomes
`mcp_tools_sql`) and appends Markdown to `$GITHUB_STEP_SUMMARY`. It is copied from
mcp_coder `main` with three adaptations: the root-package name, the docstring
examples, and a repo-specific caveat.

## Files created / modified

| Path | Action | Step |
|---|---|---|
| `pyproject.toml` | modify — deps, `[tool.deptry]`, `dev` extra, ruff per-file-ignore | 1, 2 |
| `tools/deptry_check.sh` | create (executable bit) | 1 |
| `tools/deptry_check.bat` | create | 1 |
| `.github/workflows/ci.yml` | modify — `deptry` matrix entry (1); coverage wiring (3) | 1, 3 |
| `.gitignore` | modify — coverage artefacts | 2 |
| `tools/ci_coverage_summary.py` | create | 2 |
| `tests/tools/__init__.py` | create (empty) | 2 |
| `tests/tools/test_ci_coverage_summary.py` | create | 2 |

No changes to `src/`. No docs updates (nothing in README, `docs/` or CLAUDE.md
lists CI jobs or tool scripts).

## Steps

1. [step_1.md](./step_1.md) — deptry: config, dependency cleanup, check script, CI job.
2. [step_2.md](./step_2.md) — coverage summary script + ported tests, dev deps, `.gitignore`, ruff ignore.
3. [step_3.md](./step_3.md) — CI coverage wiring: `unit-tests` job, `--cov` on integration jobs, uploads, `coverage` job.
