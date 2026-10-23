# Step 1 — deptry: config, dependency cleanup, check script, CI job

## LLM prompt
> Read `pr_info/steps/summary.md`, then implement **only** `pr_info/steps/step_1.md`.
> Make the `pyproject.toml`, `tools/` and `ci.yml` changes listed below, run the
> verification and the quality checks, then format and make exactly one commit.
> Do not start step 2.

## WHERE
- `pyproject.toml`
- `tools/deptry_check.sh` (new, executable)
- `tools/deptry_check.bat` (new)
- `.github/workflows/ci.yml` (`architecture` matrix only)

## WHAT

### `pyproject.toml`
- `dependencies`: remove `"structlog>=24.5.0"` and `"python-json-logger>=3.2.1"`.
- `[project.optional-dependencies].dev`: add `"deptry>=0.25.1",`.
- New section, placed after `[tool.pytest.ini_options]` or next to the other
  `[tool.*]` checker sections:
  ```toml
  # Run as `deptry src` (tools/deptry_check.sh) — src only; tests/ and tools/ are not scanned.
  [tool.deptry]
  known_first_party = ["mcp_tools_sql"]
  # Packages in the `dev` extra are tooling, not runtime deps: no DEP002 for them,
  # but importing one from src/ is still reported (DEP004).
  optional_dependencies_dev_groups = ["dev"]

  # pyodbc / psycopg are absent in `.[dev]`-only installs (the CI `architecture` job),
  # so deptry cannot read their metadata; name the modules explicitly.
  [tool.deptry.package_module_name_map]
  pyodbc = ["pyodbc"]
  psycopg = ["psycopg"]
  ```

### `tools/deptry_check.sh` (verbatim copy of mcp_coder `0949073a`)
```bash
#!/bin/bash
# Check dependency declarations using deptry
#
# Usage from Git Bash: ./tools/deptry_check.sh

if ! command -v deptry &> /dev/null; then
    echo "ERROR: deptry not found. Install with: uv pip install deptry"
    exit 1
fi

echo "Checking dependency declarations..."
deptry src "$@"
```

### `tools/deptry_check.bat` (verbatim copy of mcp_coder `0949073a`)
```bat
@echo off
REM Check dependency declarations using deptry
REM
REM Usage from cmd.exe: tools\deptry_check.bat

where deptry >nul 2>&1
if errorlevel 1 (
    echo ERROR: deptry not found. Install with: uv pip install deptry
    exit /b 1
)

echo Checking dependency declarations...
deptry src %*
exit /b %ERRORLEVEL%
```

### `.github/workflows/ci.yml`
Append to the `architecture` job's `matrix.check` list, after `pycycle`:
```yaml
          - {name: "deptry", cmd: "deptry --version && ./tools/deptry_check.sh"}
```

## HOW
- No Python code and no imports change. Only config, scripts and CI.
- Executable bit: after `git add tools/deptry_check.sh`, run
  `git update-index --chmod=+x tools/deptry_check.sh`. Verify with
  `mcp__mcp-workspace__git` `ls_files` and args `["-s", "tools/deptry_check.sh"]`;
  the mode must be `100755`.

## ALGORITHM
None (configuration only).

## DATA
Expected `deptry src` result: exit 0, `Success! No dependency issues found.`, and
no "Assuming the corresponding module name" warnings.

## Verification
1. If `deptry` is not installed, install it into the project environment
   (`uv pip install "deptry>=0.25.1"`).
2. Run `deptry src` (Bash; no MCP equivalent). It must be clean, with no warnings.
   - If it reports any issue other than what this step removes, write one line
     to `pr_info/.blocked.txt` naming the reported issue(s), and stop.
3. Run `mcp__mcp-tools-py__run_pylint_check`, `run_mypy_check`, and
   `run_pytest_check` with `extra_args: ["-n", "auto"]`. All must pass.
4. Run `mcp__mcp-tools-py__run_format_code`, stage, set the executable bit, and commit:
   `chore(deps): add deptry check and drop unused structlog/python-json-logger`.
