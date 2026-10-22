# Step 8 — CI: rename the ruff job and cover `tools/`

## LLM prompt
> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_8.md`.
> Change only `.github/workflows/ci.yml`. Make exactly one commit.

## WHERE
- `.github/workflows/ci.yml`, job `test`, `matrix.check` list

## WHAT
Replace
```yaml
- {name: "ruff-docstrings", cmd: "ruff version && ruff check src tests"}
```
with
```yaml
- {name: "ruff", cmd: "ruff version && ruff check src tests tools"}
```
Leave the `black`/`isort` entries (still `src tests`) unchanged — out of scope.

## HOW
No code or test changes. Branch protection still requires `ruff-docstrings`;
Marcus swaps it to `ruff` right before merging (not done by this step).

## Verification
- `run_ruff_check(target_directories=["src","tests","tools"])` → clean (the
  same scope CI now uses).
- `search_files(pattern="ruff-docstrings")` → no matches in `.github/`.
- Confirm `pr_info/.blocked.txt` does not exist and `.scratch/` is absent.

## Commit
`ci: rename ruff-docstrings job to ruff and check tools/`
