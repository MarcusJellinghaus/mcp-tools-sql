# Step 1 — Dependency floor and CI git install of mcp-coder-utils

**Reference:** [summary.md](./summary.md) §6 "Dependency tracks mcp-coder-utils `main`".

## Why

`console_level` (needed from Step 4) is on mcp-coder-utils `main` but in **no
PyPI release**. This repo publishes to PyPI, so a bare `mcp-coder-utils`
requirement would resolve to 0.1.5 for end users and crash every command.
A version floor makes that fail cleanly at resolution instead; CI and local dev
install from git so the floor is satisfiable today.

This step is configuration only — no test code.

## WHERE

- `pyproject.toml`
- `.github/workflows/ci.yml`

## WHAT

### `pyproject.toml` — three edits

1. In `[project].dependencies`, replace the bare entry:

   ```toml
   "mcp-coder-utils>=0.1.6.dev0",
   ```

2. In `[tool.uv.sources]`, uncomment **only** the mcp-coder-utils line:

   ```toml
   mcp-coder-utils = { git = "https://github.com/MarcusJellinghaus/mcp-coder-utils.git" }
   ```

3. In `[tool.mcp-coder.install-from-github].packages`, uncomment **only** the
   mcp-coder-utils entry:

   ```toml
   "mcp-coder-utils @ git+https://github.com/MarcusJellinghaus/mcp-coder-utils.git",
   ```

Leave the mcp-config-tool / mcp-workspace / mcp-coder lines commented.

### `.github/workflows/ci.yml` — five install sites

Sites and their extras (**preserve each one's extras exactly**):

| Job | Extras |
|-----|--------|
| `test` (matrix) | `.[dev]` |
| `sqlite-integration` | `.[dev]` |
| `postgresql-integration` | `.[dev,postgresql]` |
| `mssql-integration` | `.[dev,mssql]` |
| `architecture` (matrix) | `.[dev]` |

At the **first** site, write the full rationale comment:

```yaml
      - name: Install dependencies
        # mcp-coder-utils is pinned to git main: `console_level` (needed by the
        # server logging path) landed after the 0.1.5 PyPI release. Pre-install
        # it so the `mcp-coder-utils>=0.1.6.dev0` requirement in [project]
        # resolves. Keeping the URL here (not in pyproject.toml) is what lets
        # tools/check_no_url_deps.py keep passing.
        run: |
          uv pip install --system \
            "mcp-coder-utils @ git+https://github.com/MarcusJellinghaus/mcp-coder-utils.git" \
            ".[dev]"
```

At the other four sites use a one-line pointer instead of repeating the block:

```yaml
      - name: Install dependencies
        # mcp-coder-utils from git — see the comment in the `test` job.
        run: |
          uv pip install --system \
            "mcp-coder-utils @ git+https://github.com/MarcusJellinghaus/mcp-coder-utils.git" \
            ".[dev,postgresql]"
```

> Note this repo installs **non-editable** (`".[dev]"`), unlike mcp-workspace's
> `-e ".[dev]"`. Keep this repo's form.

## HOW — integration points

- `tools/check_no_url_deps.py` scans `[project].dependencies` and
  `[project.optional-dependencies]` for `git+`, ` @ http`, ` @ file`. A version
  specifier is not a URL spec, and the git URLs live in the workflow and in
  `[tool.*]` tables, so it continues to pass. **Verify this by running it.**
- `[tool.uv.sources]` and `[tool.mcp-coder.install-from-github]` are consumed by
  `tools/reinstall_local.bat` / `.sh` and `tools/read_github_deps.py` for local
  dev installs.

## DATA

No runtime data structures change.

## Exit criteria

- `python tools/check_no_url_deps.py` prints
  `OK: no direct URL dependencies in [project]` and exits 0.
- `mcp__tools-py__run_pylint_check`, `mcp__tools-py__run_pytest_check`,
  `mcp__tools-py__run_mypy_check` all pass (unchanged from baseline — this step
  touches no Python).
- `./tools/format_all.sh` run before committing.

## LLM prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_1.md`.
>
> Implement Step 1 only: pin `mcp-coder-utils` to a `>=0.1.6.dev0` floor in
> `pyproject.toml`, uncomment the mcp-coder-utils entries in
> `[tool.uv.sources]` and `[tool.mcp-coder.install-from-github]` (leave the
> other packages commented), and add a git pre-install of mcp-coder-utils to
> all five `uv pip install` sites in `.github/workflows/ci.yml`, preserving
> each site's existing extras. Write the full rationale comment once at the
> first site and a one-line pointer at the other four.
>
> Use MCP tools for all file operations. Then run
> `python tools/check_no_url_deps.py` and the three MCP quality checks
> (`run_pylint_check`, `run_pytest_check` with
> `extra_args=["-n","auto"]`, `run_mypy_check`) and confirm they pass.
> Do not touch any Python source file in this step.
