# Step 9 — black and isort CI cover `tools/`

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_9.md` exactly.
> Extend the black and isort CI commands to `tools`. Run format (check mode on
> `src tests tools`), pylint, pytest (`-n auto`), mypy; all must pass. Produce exactly one commit.

## WHERE

- `.github/workflows/ci.yml` — `test` matrix, `black` and `isort` entries

## WHAT

```yaml
          - {name: "black", cmd: "black --version && black --check src tests tools"}
          - {name: "isort", cmd: "isort --version && isort --check --profile=black --float-to-top src tests tools"}
```

Same commands as mcp_coder's `ci.yml`.

## HOW

- `mcp__mcp-tools-py__run_format_code(target_directories=["src", "tests", "tools"], check_only=True)` → clean. If `tools/` needs reformatting, run `run_format_code(target_directories=["tools"])` and include the result in this commit.

## DATA

None.

## Checks

- format check clean on `src tests tools`; pylint, pytest (`-n auto`), mypy pass.
- Final acceptance sweep:
  - `mcp__mcp-workspace__search_files(pattern="git\\+https", glob=".github/workflows/*.yml")` → no matches.
  - `run_pylint_check(target_directories=["src", "tests"])` clean; `run_lint_imports_check` passes.

## Commit

`ci: run black and isort on tools`
