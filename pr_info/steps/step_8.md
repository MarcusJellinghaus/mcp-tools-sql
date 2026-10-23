# Step 8 — Local check scripts; CI architecture jobs call them

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_8.md` exactly.
> Copy the 10 scripts from mcp_coder's `tools/` verbatim, set the executable bit on
> the 4 CI-invoked `.sh` files, and point the CI `architecture` matrix at them.
> Run lint-imports, tach, vulture, format, pylint, pytest (`-n auto`), mypy; all must pass.
> Produce exactly one commit.

## WHERE

New files in `tools/`, each copied byte-for-byte from `mcp_coder:tools/<same name>`
(read with `mcp__mcp-workspace__read_reference_file(reference_name="mcp_coder", ...)`):

| Script | Command it runs | CI-invoked | Exec bit |
|---|---|---|---|
| `lint_imports.sh` / `.bat` | `lint-imports` | yes | `.sh` +x |
| `tach_check.sh` / `.bat` | `tach check` | yes | `.sh` +x |
| `pycycle_check.sh` / `.bat` | `pycycle --here --ignore .venv,__pycache__,build,dist,.git,.pytest_cache,.mypy_cache` | yes | `.sh` +x |
| `vulture_check.sh` / `.bat` | `vulture src tests vulture_whitelist.py --min-confidence 60` | yes | `.sh` +x |
| `ruff_check.sh` / `.bat` | `ruff check src tests tools` | no (local only) | none |

Modify `.github/workflows/ci.yml` — `architecture` job matrix.

## Precondition

Each copied script's command must equal the current CI command in the table above. If a blueprint script runs a different command (or references a path that doesn't exist here: `vulture_whitelist.py`, `tach.toml`, `.importlinter`), write one line to `pr_info/.blocked.txt` naming the script and stop.

## WHAT — CI matrix

```yaml
        check:
          - {name: "import-linter", cmd: "lint-imports --help > /dev/null && ./tools/lint_imports.sh"}
          - {name: "tach", cmd: "tach --version && ./tools/tach_check.sh"}
          - {name: "vulture", cmd: "vulture --version && ./tools/vulture_check.sh"}
          - {name: "pycycle", cmd: "pycycle --version && ./tools/pycycle_check.sh"}
```

The CI `ruff` job (in the `test` matrix) keeps calling `ruff check src tests tools` directly, as in mcp_coder.

## HOW — executable bit

Files created on Windows are staged as `100644`; CI's `./tools/x.sh` would fail with "Permission denied". When committing:

```
git add tools/
git add --chmod=+x tools/lint_imports.sh tools/tach_check.sh tools/pycycle_check.sh tools/vulture_check.sh
```

Verify: `mcp__mcp-workspace__git(command="ls_files", args=["-s"], pathspec=["tools/"])` shows `100755` for those 4 files and `100644` for `ruff_check.sh` and all `.bat` files.

## DATA

None.

## Checks

- `run_lint_imports_check`, `run_tach_check`, `run_vulture_check` pass (same commands as the scripts).
- format, pylint, pytest (`-n auto`), mypy pass.

## Commit

`chore(tools): add local check scripts and call them from CI`
