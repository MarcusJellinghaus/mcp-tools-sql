# Summary — Issue #83: Align pylint, pytest, CI install and check scripts with mcp_coder

Part of MarcusJellinghaus/mcp_coder#1163. Blueprint: the `mcp_coder` reference project
(read it with `mcp__mcp-workspace__read_reference_file(reference_name="mcp_coder", ...)`).

## Goal

Bring this repo's quality gates and CI plumbing in line with mcp_coder:

- pylint runs fully (not `-E` only) with mcp_coder's disable list and `R0401` enabled.
- pytest `addopts` match mcp_coder.
- CI installs GitHub deps from `[tool.mcp-coder.install-from-github]` — no hardcoded git URLs in workflows.
- The upstream workflow becomes an "upstream compat check": mypy **and** a runtime import of every `mcp_tools_sql` module.
- `mcp_coder_utils` may only be imported through `mcp_tools_sql.utils` shims — enforced by import-linter.
- Local `tools/*.sh` / `.bat` check scripts; CI `architecture` jobs call the same scripts.
- black/isort CI also covers `tools/`.

## Architectural / design changes

| Change | Before | After |
|---|---|---|
| Backend factory location | `create_backend()` in `backends/base.py`, lazily importing `sqlite`/`mssql` → pylint `R0401` cycle `base → sqlite/mssql → base` | `create_backend()` in `backends/registry.py` (its only `backends/` importer). Import graph: `registry → base`, `registry → sqlite/mssql (lazy) → base`. No back edge. `base.py` keeps `_DIALECTS`, `to_dialect`, `DatabaseBackend` |
| Shared-library boundary | Convention only (CLAUDE.md claimed a contract that didn't enforce it) | import-linter `mcp_coder_utils_isolation` contract: only `mcp_tools_sql.utils.**` may import `mcp_coder_utils`. Three shims: `log_utils`, `user_app_data`, new `subprocess_runner` |
| GitHub dep source for CI | URL hardcoded in 6 workflow install steps | `[tool.mcp-coder.install-from-github]` via `python tools/read_github_deps.py --specs` (CI single source of truth; `[tool.uv.sources]` stays for `uv sync`) |
| Upstream break detection | `upstream-mypy-check.yml`: mypy only | `upstream-compat-check.yml`: mypy + strict import walk, each gated on install success so one failure doesn't hide the other |
| Import-health test | none | `tests/test_module_imports.py` runs `tests/_import_walker.py` in a fresh interpreter (`python -P`) so conftest `sys.modules` mocks (e.g. fake `pyodbc`) can't mask breaks. Non-strict in normal runs (missing optional extras → warning), strict (`MCP_TOOLS_SQL_IMPORT_TEST_STRICT=1`) in the compat workflow |
| Local vs CI checks | CI architecture jobs inline commands | CI calls `./tools/<check>.sh`; developers run the same scripts |

No runtime behaviour of the MCP server changes.

## Files

### Created
- `src/mcp_tools_sql/utils/subprocess_runner.py` — shim re-exporting `execute_subprocess`, `CommandOptions`
- `tests/_import_walker.py` — stdlib-only walker (port from mcp_coder)
- `tests/test_module_imports.py` — walker unit tests + full import test (port from mcp_coder)
- `.github/workflows/upstream-compat-check.yml` — moved from `upstream-mypy-check.yml`
- `tools/ruff_check.sh`, `tools/ruff_check.bat` (local only)
- `tools/lint_imports.sh`, `tools/lint_imports.bat`
- `tools/tach_check.sh`, `tools/tach_check.bat`
- `tools/pycycle_check.sh`, `tools/pycycle_check.bat`
- `tools/vulture_check.sh`, `tools/vulture_check.bat`

### Modified
- `pyproject.toml` — pylint `disable`/`enable`; pytest `addopts`
- `src/mcp_tools_sql/backends/base.py` — `create_backend` removed; comments updated
- `src/mcp_tools_sql/backends/registry.py` — `create_backend` added
- `tests/test_smoke.py`, `tests/verification/test_connection.py` — import `create_backend` from `registry`
- `tests/test_sql_placeholders.py`, `tests/verification/test_config_files.py` — merge split string literals
- `tests/test_schema_tools_multitarget.py` — `_FanoutBackend` stubs raise `AssertionError`
- `tools/read_github_deps.py` — replaced with mcp_coder's version
- `.github/workflows/ci.yml` — pylint full run, install via `--specs`, architecture jobs call scripts, black/isort cover `tools`, pytest drops redundant `-n auto`
- `.importlinter` — `include_external_packages`, new contract
- `.claude/CLAUDE.md` — "Shared Libraries" section

### Deleted (moved)
- `.github/workflows/upstream-mypy-check.yml`

## Step map

The issue groups the work into 6 steps. Independent parts are split into separate commits here (one commit per step file):

| Step file | Issue step | Content |
|---|---|---|
| step_1 | 1 | Move `create_backend` to `registry.py` (R0401 fix) |
| step_2 | 1 | pylint config + W1404/W0223 fixes + CI full pylint run |
| step_3 | 2 | pytest `addopts` |
| step_4 | 3 | `read_github_deps.py` port + CI installs via `--specs` |
| step_5 | 4 | `subprocess_runner` shim + import walker test |
| step_6 | 4 | `upstream-compat-check.yml` |
| step_7 | 4 | import-linter `mcp_coder_utils_isolation` + CLAUDE.md |
| step_8 | 5 | `tools/*` check scripts + CI architecture jobs |
| step_9 | 6 | black/isort CI on `src tests tools` |

## Constraints (apply to all steps)

- Use MCP tools (see `.claude/CLAUDE.md`). Pytest: `extra_args: ["-n", "auto"]`.
- After each step: `run_format_code`, then pylint, pytest, mypy must pass; plus any step-specific check.
- Executable bit for CI-invoked `.sh` files: `git add --chmod=+x <file>` (approved `git add`; not `git update-index`).
- `[tool.uv.sources]` keeps its git URL — keep it in sync with `[tool.mcp-coder.install-from-github]`.
- Out of scope: ruff format / ruff `I` migration, `format_all` script, deptry (#82).
- If a stated precondition does not hold, write one line to `pr_info/.blocked.txt` and stop.
