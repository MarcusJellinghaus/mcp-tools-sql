# Step 1 — Dependency floor and CI git install of mcp-coder-utils

**Reference:** [summary.md](./summary.md) §6 "Dependency tracks mcp-coder-utils `main`".

## Why

`console_level` (needed from Step 4) is on mcp-coder-utils `main` but in **no
PyPI release**. This repo publishes to PyPI, so a bare `mcp-coder-utils`
requirement would resolve to 0.1.5 for end users and crash every command.
A version floor makes that fail cleanly at resolution instead; CI and local dev
install from git so the floor is satisfiable today.

This step also upgrades the developer's venv to that same git `main`, because
the floor declared here is only meaningful if the environment can satisfy it.
The shared dev venv currently has `mcp-coder-utils 0.1.5.dev4+g67c11cc76` —
before `console_level`. Skip the upgrade and Step 4 fails with
`TypeError: setup_logging() got an unexpected keyword argument 'console_level'`,
which reads like a code bug rather than a stale dependency.

This step is configuration only — no test code.

## WHERE

- `pyproject.toml`
- `.github/workflows/ci.yml`
- `tools/reinstall_local.sh` / `.bat` (only if the verification below fails —
  see "Install-order risk")
- the local virtual environment

## WHAT

### 1. `pyproject.toml` — three edits

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

### 2. `.github/workflows/ci.yml` — five install sites

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

### 3. Upgrade the local venv to mcp-coder-utils `main`

Do this **after** the `pyproject.toml` edits, so the uncommented
`[tool.mcp-coder.install-from-github]` entry drives it:

```
source tools/reinstall_local.sh
```

or, to upgrade the single package without a full reinstall:

```
uv pip install --force-reinstall --no-deps "mcp-coder-utils @ git+https://github.com/MarcusJellinghaus/mcp-coder-utils.git"
```

Then confirm the installed `setup_logging` accepts a `console_level` keyword —
Steps 3 and 4 both depend on it.

## HOW — integration points

- `tools/check_no_url_deps.py` scans `[project].dependencies` and
  `[project.optional-dependencies]` for `git+`, ` @ http`, ` @ file`. A version
  specifier is not a URL spec, and the git URLs live in the workflow and in
  `[tool.*]` tables, so it continues to pass. **Verify this by running it.**
- `[tool.uv.sources]` and `[tool.mcp-coder.install-from-github]` are consumed by
  `tools/reinstall_local.bat` / `.sh` and `tools/read_github_deps.py` for local
  dev installs.

### Install-order risk — verify, do not assume

The floor is only useful if both install paths can actually satisfy it, and
neither is exercised by the usual quality checks (pylint/pytest/mypy do not
re-resolve dependencies). Two things to prove by running them:

1. **Local dev.** `tools/reinstall_local.sh:56` installs this project
   (`uv pip install -e ".[dev,all-backends]"`, step 2/5) **before** applying the
   GitHub overrides (step 3/5). Against PyPI's 0.1.5 the new
   `>=0.1.6.dev0` floor may therefore fail at resolution before the git install
   ever runs — unless `uv pip install -e .` honours the newly uncommented
   `[tool.uv.sources]`. If the run fails this way, **reordering
   `reinstall_local.sh` and `reinstall_local.bat` so the GitHub overrides are
   installed before the project is in scope for this step.**
2. **CI.** The git install must produce a setuptools-scm version that sorts at
   or above `0.1.6.dev0`. `mcp-workspace` uses the same git-install step but
   carries **no floor**, so this is unproven in the ecosystem — check the
   resolved version rather than assuming it.

## DATA

No runtime data structures change.

## Exit criteria

- `python tools/check_no_url_deps.py` prints
  `OK: no direct URL dependencies in [project]` and exits 0.
- The local venv install path succeeds end to end: `tools/reinstall_local.sh`
  runs without error and `uv pip show mcp-coder-utils` reports a version that
  satisfies `>=0.1.6.dev0`.
- The installed `mcp_coder_utils.log_utils.setup_logging` accepts a
  `console_level` keyword.
- `mcp__mcp-tools-py__run_pylint_check`, `mcp__mcp-tools-py__run_pytest_check`,
  `mcp__mcp-tools-py__run_mypy_check` all pass (unchanged from baseline — this
  step touches no Python).
- `mcp__mcp-tools-py__run_format_code` run before committing.

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
> Then upgrade the local venv to mcp-coder-utils git `main` and verify the
> installed `setup_logging` accepts a `console_level` keyword, and that
> `uv pip show mcp-coder-utils` reports a version satisfying `>=0.1.6.dev0`.
> If `tools/reinstall_local.sh` fails at resolution because it installs the
> project before applying the GitHub overrides, reorder that script (and the
> `.bat`) so the overrides come first — that fix is part of this step.
>
> Use MCP tools for all file operations. Then run
> `python tools/check_no_url_deps.py` and the three MCP quality checks
> (`run_pylint_check`, `run_pytest_check` with
> `extra_args=["-n","auto"]`, `run_mypy_check`) and confirm they pass.
> Do not touch any Python source file under `src/` or `tests/` in this step.
