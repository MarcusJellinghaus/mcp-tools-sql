# Step 4 — CI installs GitHub deps from `[tool.mcp-coder.install-from-github]`

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_4.md` exactly.
> Port `tools/read_github_deps.py` from mcp_coder verbatim, then replace every
> hardcoded `mcp-coder-utils @ git+…` install in the workflows with `--specs`.
> Run format, ruff, pylint, pytest (`-n auto`), mypy; all must pass. Produce exactly one commit.

## WHERE

- `tools/read_github_deps.py` (replace)
- `.github/workflows/ci.yml` (5 jobs: `test`, `sqlite-integration`, `postgresql-integration`, `mssql-integration`, `architecture`)
- `.github/workflows/upstream-mypy-check.yml` (install step only; it is renamed in step 6)

## WHAT

`tools/read_github_deps.py` — copy byte-for-byte from `mcp_coder:tools/read_github_deps.py`:

```python
def main() -> None:
    """Read GitHub install config and print uv pip install commands."""
```

## ALGORITHM (`main`)

```
path = <repo>/pyproject.toml; if missing: return
gh = data["tool"]["mcp-coder"]["install-from-github"] (default {})
if "--specs" in argv: print each spec in gh["packages"], one per line; return
if packages: print 'uv pip install "p1" "p2"'
if packages-no-deps: print 'uv pip install --no-deps "p3"'
```

## DATA

- Default output (unchanged for this repo, so `tools/reinstall_local.*` keep working):
  `uv pip install "mcp-coder-utils @ git+https://github.com/MarcusJellinghaus/mcp-coder-utils.git"`
- `--specs` output: `mcp-coder-utils @ git+https://github.com/MarcusJellinghaus/mcp-coder-utils.git`

## HOW (workflows)

Every install step becomes (keep each job's extras: `.[dev]`, `.[dev,postgresql]`, `.[dev,mssql]`):

```yaml
      - name: Install dependencies
        # GitHub-installed deps come from [tool.mcp-coder.install-from-github]
        # in pyproject.toml (installed in the same uv call so they win over PyPI).
        run: |
          mapfile -t SPECS < <(python tools/read_github_deps.py --specs)
          uv pip install --system "${SPECS[@]}" ".[dev]"
```

- `test` job: replace the whole "mcp-coder-utils is pinned to git main … check_no_url_deps.py keep passing." comment with the 2-line comment above.
- Other ci.yml jobs: replace `# mcp-coder-utils from git — see the comment in the `test` job.` with `# GitHub deps from [tool.mcp-coder.install-from-github] — see the `test` job.`
- `upstream-mypy-check.yml`: same `mapfile` form with `".[dev]"`; comment → `# GitHub deps from [tool.mcp-coder.install-from-github] in pyproject.toml.`
- Do **not** touch `[tool.uv.sources]` in `pyproject.toml` (used by `uv sync`).

## Checks

- `mcp__mcp-workspace__search_files(pattern="git\\+https", glob=".github/workflows/*.yml")` → no matches.
- `run_ruff_check` (covers `tools`), format, pylint, pytest (`-n auto`), mypy pass.

## Commit

`ci: install GitHub deps from pyproject via read_github_deps --specs`
