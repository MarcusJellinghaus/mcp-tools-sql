# Step 6 — Upstream compat check workflow

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_6.md` exactly.
> Steps 4 (`--specs`) and 5 (`tests/test_module_imports.py`) must already be committed.
> Move the upstream workflow and add the strict import step. Run format, pylint,
> pytest (`-n auto`), mypy; all must pass. Produce exactly one commit.

## Precondition

`tests/test_module_imports.py` exists and `tools/read_github_deps.py` supports `--specs`. If not, write one line to `pr_info/.blocked.txt` and stop.

## WHERE

- `.github/workflows/upstream-mypy-check.yml` → `.github/workflows/upstream-compat-check.yml` (use `mcp__mcp-workspace__move_file`, keeps history)

## WHAT — full file content after the move

```yaml
name: Upstream compat check

# Triggered by repository_dispatch when mcp-coder-utils' main branch changes.
# Runs mypy --strict and a runtime import check of every mcp_tools_sql module
# against the latest mcp-coder-utils main to detect interface breaks.
# On failure: standard GitHub Actions email + red icon in the Actions tab.

on:
  repository_dispatch:
    types: [upstream-main-updated]
  workflow_dispatch:
    inputs:
      upstream:
        description: 'Upstream that triggered this run (shown in the job name)'
        required: false
        default: 'manual'

permissions:
  contents: read

jobs:
  upstream-compat:
    name: upstream-compat-${{ github.event.client_payload.upstream || github.event.inputs.upstream || github.event_name }}
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: astral-sh/setup-uv@v7
        with:
          enable-cache: false
      - uses: actions/setup-python@v6
        with:
          python-version: "3.11"

      # Upstream specs come from [tool.mcp-coder.install-from-github] and are
      # installed in the same call as .[dev], so uv keeps the git versions.
      - name: Install upstream packages from main and mcp-tools-sql
        id: install
        run: |
          mapfile -t SPECS < <(python tools/read_github_deps.py --specs)
          uv pip install --system "${SPECS[@]}" ".[dev]"

      - name: Run mypy --strict
        if: ${{ !cancelled() && steps.install.outcome == 'success' }}
        run: mypy --strict src tests

      - name: Import every mcp_tools_sql module (strict)
        if: ${{ !cancelled() && steps.install.outcome == 'success' }}
        env:
          MCP_TOOLS_SQL_IMPORT_TEST_STRICT: "1"
        run: pytest tests/test_module_imports.py
```

## HOW

- Keep `enable-cache: false` and `setup-python@v6` (repo convention, #85).
- `--specs` instead of mcp_coder's hardcoded URLs is a deliberate deviation (issue Decisions).
- Rename is safe: mcp-coder-utils' `notify-downstream.yml` dispatches the event type `upstream-main-updated`, not a filename.

## DATA

None.

## Checks

- `mcp__mcp-workspace__search_files(pattern="upstream-mypy")` → no matches.
- `mcp__mcp-workspace__search_files(pattern="git\\+https", glob=".github/workflows/*.yml")` → no matches.
- format, pylint, pytest (`-n auto`), mypy pass.
- After the PR is pushed, the workflow's `workflow_dispatch` run is the acceptance check (done by the human).

## Commit

`ci: rename upstream-mypy-check to upstream-compat-check, add import check`
