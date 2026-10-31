# Quality and Security Checks

Which automated checks run on mcp-tools-sql, and why. Details stay in the linked config
files. Modelled on mcp_coder's `docs/repository-setup/quality-and-security-checks.md`.

## Overview

| Area | Tool(s) | Why | MCP tool | Links |
|---|---|---|---|---|
| [Lint](#lint) | ruff | Bugs, style and docstring gaps in one fast pass | `run_ruff_check` | [`pyproject.toml`](../pyproject.toml), [`ci.yml`](../.github/workflows/ci.yml) |
| [Formatting](#formatting) | ruff format, ruff `I` | One tool for layout and import order | `run_format_code` | [`pyproject.toml`](../pyproject.toml), [`ci.yml`](../.github/workflows/ci.yml) |
| [Types](#types) | mypy strict | Type errors, including breaks from upstream packages | `run_mypy_check` | [`pyproject.toml`](../pyproject.toml), [`ci.yml`](../.github/workflows/ci.yml), [`upstream-compat-check.yml`](../.github/workflows/upstream-compat-check.yml) |
| [Pylint](#pylint) | pylint | Errors and warnings ruff does not cover | `run_pylint_check` | [`pyproject.toml`](../pyproject.toml), [`ci.yml`](../.github/workflows/ci.yml) |
| [Architecture](#architecture) | import-linter, tach, vulture, pylint `R0401` | Module boundaries, no cycles, no dead code | `run_lint_imports_check`, `run_tach_check`, `run_vulture_check` | [`.importlinter`](../.importlinter), [`tach.toml`](../tach.toml), [`ci.yml`](../.github/workflows/ci.yml), [`architecture.md`](architecture/architecture.md) |
| [File size](#file-size) | `mcp-coder check file-size` | Small files fit an LLM's context window | `check_file_size` | [`.large-files-allowlist`](../.large-files-allowlist), [`ci.yml`](../.github/workflows/ci.yml) |
| [Dependencies](#dependencies) | deptry, Dependabot | Declared dependencies match imports; stay current | `run_deptry_check`; Dependabot: none | [`pyproject.toml`](../pyproject.toml), [`dependabot.yml`](../.github/dependabot.yml) |
| [Coverage](#coverage) | pytest-cov, diff-cover | Show what tests reach, without gating | `run_pytest_check` | [`ci.yml`](../.github/workflows/ci.yml), [`ci_coverage_summary.py`](../tools/ci_coverage_summary.py) |
| [Security scanning](#security-scanning) | ruff `S`, `PLE2502`, CodeQL, OpenSSF Scorecard | Insecure code and supply-chain risks | `run_ruff_check`; CodeQL, Scorecard: none | [`pyproject.toml`](../pyproject.toml), [`scorecard.yml`](../.github/workflows/scorecard.yml), [`SECURITY.md`](../SECURITY.md) |
| [Tests](#tests) | pytest | Behaviour stays correct | `run_pytest_check` | [`pyproject.toml`](../pyproject.toml), [`ci.yml`](../.github/workflows/ci.yml) |
| [Repo hygiene](#repo-hygiene) | CI jobs, `tools/check_*.py` | Keep scratch files and URL dependencies out | none | [`ci.yml`](../.github/workflows/ci.yml), [`check_no_url_deps.py`](../tools/check_no_url_deps.py) |
| [Repo settings](#repo-settings-manual-github-ui) | `mcp-coder verify`, branch ruleset | GitHub security features and required checks are on | none | [Checklist](#repo-settings-manual-github-ui) |
| [Badges](#badges) | README badges | Check state visible at a glance | none | [`README.md`](../README.md) |

## Principles

- Every enabled or rejected choice has a recorded reason, in the config comment or its issue.
- A rule that starts firing later is either fixed or ignored with a reason. It is never
  suppressed silently.

## Tool support

- **mcp-tools-py** runs the checks locally: `run_ruff_check`, `run_ruff_fix`,
  `run_pylint_check`, `run_mypy_check`, `run_pytest_check`, `run_vulture_check`,
  `run_lint_imports_check`, `run_tach_check`, `run_deptry_check`, `run_format_code`.
- **mcp-workspace** reads CI and PR status (`check_branch_status`, `github_pr_view`) and
  provides `check_file_size`.
- **Gaps** (shell, mcp-coder CLI or CI only): the [Repo hygiene](#repo-hygiene)
  jobs, CodeQL, Scorecard, Dependabot, `mcp-coder verify`.

## Lint

ruff, rule set in [`pyproject.toml`](../pyproject.toml) `[tool.ruff.lint]`: `D` (Google
convention), `ANN`, selected `DOC`, `SIM`, `E`, `F`, `C4`, `B`, `S`, `UP`, `I`, `PLW1510`
and `PLE2502`. `TRY`, `EM` and the rest of `PL` were rejected in mcp_coder (#1172, #1181);
`PL` is not selected wholesale because it would re-enable pylint's disabled `R` category.

Gotcha: `explicit-preview-rules = true`, so preview rules fire only when selected by exact
code. A bare `DOC` or `SIM905`-style prefix enforces nothing; list `DOC201`, `SIM905` etc.
individually.

CI job `ruff`, over `src`, `tests` and `tools`.

## Formatting

`ruff format` plus ruff `I` replaced black and isort: one tool, no two sorters disagreeing.
CI jobs `ruff-format` (layout) and `ruff` (import order). `run_format_code` runs both
locally (`[tool.mcp-tools-py] formatter = "ruff"`).

## Types

mypy strict (`[tool.mypy]`), CI job `mypy` over `src` and `tests`.
[`upstream-compat-check.yml`](../.github/workflows/upstream-compat-check.yml) runs mypy
strict and a runtime import of every module against upstream main of mcp-coder-utils, on
`repository_dispatch` or `workflow_dispatch`, so interface breaks show before a release.

## Pylint

Errors and warnings; `C` and `R` are off except `R0401` (cyclic imports). Runs alongside
ruff because ruff does not fully cover pylint. CI job `pylint`. See
[`pyproject.toml`](../pyproject.toml) `[tool.pylint.messages_control]`.

## Architecture

PR-only `architecture` matrix, one job per tool:

| Job | Config | Script |
|---|---|---|
| `import-linter` | [`.importlinter`](../.importlinter) | [`lint_imports.sh`](../tools/lint_imports.sh) |
| `tach` | [`tach.toml`](../tach.toml) | [`tach_check.sh`](../tools/tach_check.sh) |
| `vulture` | `vulture_whitelist.py` | [`vulture_check.sh`](../tools/vulture_check.sh) |
| `deptry` | `[tool.deptry]` | [`deptry_check.sh`](../tools/deptry_check.sh) |

Pylint `R0401` catches cyclic imports on every push (pycycle was dropped as redundant,
as in mcp_coder). The `mcp_coder_utils_isolation` import-linter contract
keeps `mcp_coder_utils` behind the shims in `mcp_tools_sql.utils`. See
[`architecture.md`](architecture/architecture.md).

## File size

Small files suit an LLM's limited context window. CI job `file-size` runs
`mcp-coder check file-size --max-lines 750 --allowlist-file .large-files-allowlist`.
Locally `check_file_size` applies the same allowlist. The allowlist is empty: do not add
entries, split the file.

## Dependencies

deptry (`[tool.deptry]`) checks that declared dependencies match the imports in `src`;
PR-only CI job `deptry`. Dependabot updates `pip` and `github-actions` weekly
([`dependabot.yml`](../.github/dependabot.yml)).

## Coverage

Reported, never a gate. Jobs `unit-tests`, `sqlite-integration`, `postgresql-integration`
and `mssql-integration` each upload a `.coverage.*` file. The `coverage` job combines
them and, on PRs, writes a diff-cover summary to the job summary. Without coverage data
the job writes a "no coverage data" note and still succeeds. Local digest:
`run_pytest_check(coverage=True)`.

### Coverage badge

On every push to `main`, the `coverage` job writes the combined total to a public gist
(`Update coverage badge` step, `continue-on-error`, so a broken token never fails CI);
shields.io renders the README badge from the gist's raw URL. The step is skipped when
there is no coverage data.

The gist is **shared with mcp_coder** (ID `9a7892066964f11765a07d74285ad104`, one file per
repo). The filename here must stay `mcp-tools-sql-coverage.json`; `mcp_coder-coverage.json`
would overwrite mcp_coder's badge. One-time setup, mirroring mcp_coder's
`docs/repository-setup/github.md` "Coverage badge":

1. Create the gist file `mcp-tools-sql-coverage.json` in the shared gist, with placeholder
   content `{"schemaVersion": 1, "label": "coverage", "message": "pending", "color": "lightgrey"}`.
2. Create a fine-grained PAT with the account permission **Gists: read and write** only,
   repository access "Public repositories" (read-only), no expiration. The PAT must belong
   to the gist's owner account (same account as mcp_coder's, so the existing owner works).
3. Add repo secret `BADGE_GIST_TOKEN` = the PAT and repo variable `BADGE_GIST_ID` =
   `9a7892066964f11765a07d74285ad104`.

The badge shows missing or "pending" until the first push to `main` after setup. If the PAT
is replaced by an expiring one, the badge silently stops updating on expiry.

## Security scanning

- ruff `S` (flake8-bandit port) and `PLE2502` (bidirectional Unicode, covers bandit
  `B613`). Per-file ignores for tests are documented in `pyproject.toml`.
- OpenSSF Scorecard ([`scorecard.yml`](../.github/workflows/scorecard.yml)) runs weekly
  and on pushes to main, and uploads SARIF to code scanning.
- CodeQL is meant to run as GitHub default setup (no workflow file); enable it in the
  UI, see [Repo settings](#repo-settings-manual-github-ui).
- All actions are pinned to commit SHAs; Dependabot keeps the pins current.
- `approve-command.yml` runs `/approve` only for `OWNER`, `MEMBER` and `COLLABORATOR`
  comment authors.
- Vulnerability reporting policy: [`SECURITY.md`](../SECURITY.md).

`mcp-coder verify` reports CodeQL `[OK]` only because Scorecard's `upload-sarif` step
matches the `github/codeql-action/*` prefix. Default setup itself is not detected.

## Tests

pytest, split by marker: `unit-tests` (no integration markers), `sqlite-integration`,
`postgresql-integration` (Postgres 16 service container) and `mssql-integration` (SQL
Server 2022 service container, `continue-on-error`, best-effort). Exit code 5 (no tests
collected) counts as success for the integration jobs. See `[tool.pytest.ini_options]`
in [`pyproject.toml`](../pyproject.toml).

## Repo hygiene

- `check-forbidden-folders` (PR-only): blocks `pr_info/` and `.scratch/`.
- `no-url-deps` ([`check_no_url_deps.py`](../tools/check_no_url_deps.py)): no direct URL
  dependencies in `[project]` dependencies or extras; PyPI rejects them.
- `forbidden-calls` (mcp_coder's text scan for literal `["git", ...]` argv lists and
  direct `mcp_workspace` imports) was evaluated and not ported: this repo has no git
  subprocess code, and the `mcp_coder_utils_isolation` import-linter contract already
  covers the shim boundary.

## Repo settings (manual, GitHub UI)

`mcp-coder verify` reports the `GITHUB SECURITY` section; turning features on happens in
the GitHub UI under Settings. Checklist:

- [ ] Code security: CodeQL, default setup
- [ ] Code security: private vulnerability reporting
- [ ] Code security: Dependabot alerts and Dependabot security updates
- [ ] Code security: secret scanning and push protection
- [ ] Rules: branch ruleset on `main` (require PR, block force push and deletion,
  required status checks below, strict mode)
- [ ] General: auto-delete head branches on merge
- [ ] Secrets and variables: repo secret `BADGE_GIST_TOKEN` (fine-grained PAT, only
  "Gists: read and write") and repo variable `BADGE_GIST_ID` =
  `9a7892066964f11765a07d74285ad104`, plus the gist file `mcp-tools-sql-coverage.json`
  (see [Coverage badge](#coverage-badge))

Required status checks (names as reported by CI):

| Source | Check names |
|---|---|
| `test` matrix | `ruff-format`, `pylint`, `ruff`, `mypy`, `no-url-deps`, `file-size` |
| `architecture` matrix (PR-only) | `import-linter`, `tach`, `vulture`, `deptry` |
| Jobs | `check-forbidden-folders` (PR-only), `unit-tests`, `sqlite-integration`, `postgresql-integration` |

Do not require `mssql-integration` (`continue-on-error`) or `coverage` (reporting only).

**Job-name rule:** required status checks must match CI job names. Matrix entries report
under their `name`, not the job id (`test`, `architecture`). A renamed or removed job
blocks every PR until the ruleset is updated.

## Badges

README badges give the check state at a glance: CI, PyPI, Python version, license, ruff,
mypy, architecture, coverage ([setup](#coverage-badge)), OpenSSF Scorecard. TODO: add the
CodeQL badge once CodeQL default setup is enabled (it is omitted until then).
