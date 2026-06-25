# Step 4 — `pycycle` cyclic-import check (architecture matrix)

See `pr_info/steps/summary.md` (item 4). One commit.

## WHERE
- Modify `.github/workflows/ci.yml` → `architecture` job `matrix.check`

## WHAT
Add the pycycle check inline (no wrapper script — this repo uses none). The
`--ignore` list is copied verbatim from `mcp_coder`'s `pycycle_check.sh`:

```yaml
          - {name: "pycycle", cmd: "pycycle --version && pycycle --here --ignore .venv,__pycache__,build,dist,.git,.pytest_cache,.mypy_cache"}
```

`pycycle>=0.0.8` is kept in `[dev]` (step 1), so it is installed. The `architecture`
job is gated `if: github.event_name == 'pull_request'`, so pycycle runs **PR-only**
(like import-linter / tach / vulture) — intended.

## HOW
Append the entry to the existing `architecture` matrix (after `vulture`). No other
job changes.

## ALGORITHM
N/A — one matrix line.

## DATA
None.

## Verification (the "test" for this step)
- Run `pycycle --here --ignore .venv,__pycache__,build,dist,.git,.pytest_cache,.mypy_cache`
  from the repo root. Expect **no cycles found**.
- **If a pre-existing import cycle is surfaced**, fix it minimally (smallest local
  refactor: move the offending import inside a function, or break the back-edge). A
  cycle fix would touch `src/` — keep it minimal and re-run the layered checks
  (`lint-imports`, `tach check`) to confirm contracts still hold.
- Standard pylint/pytest/mypy via MCP tools — green.

## LLM prompt
> Read `pr_info/steps/summary.md` and `pr_info/steps/step_4.md`. Add the `pycycle`
> matrix entry to the `architecture` job in `.github/workflows/ci.yml`. Run pycycle
> locally with the exact `--ignore` list and confirm no cycles are found; if a cycle
> is reported, fix it with the smallest possible change and re-verify import-linter
> and tach. Run the standard MCP quality checks. Commit as one change.
