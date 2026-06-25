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

**No pre-existing cycle.** A local pycycle run
(`pycycle --here --ignore .venv,__pycache__,build,dist,.git,.pytest_cache,.mypy_cache`)
confirmed **no cycles** in this repo. So this step is **purely the matrix-entry
addition** — no `src/` changes are expected, and the cycle-fix commit that would
otherwise precede it is not needed. (If a future run ever surfaces a cycle, fix it
in a separate preceding commit — not bundled into this CI-config commit.)

## HOW
Append the entry to the existing `architecture` matrix (after `vulture`). No other
job changes.

## ALGORITHM
N/A — one matrix line.

## DATA
None.

## Verification (the "test" for this step)
- Run `pycycle --here --ignore .venv,__pycache__,build,dist,.git,.pytest_cache,.mypy_cache`
  from the repo root. **No cycles found** (already confirmed locally — see above).
  This step therefore adds only the matrix line; no `src/` edits.
- (Contingency only — not expected here:) if a future run ever surfaces a cycle,
  the fix must be a **separate, earlier commit** (smallest local refactor: move the
  offending import inside a function, or break the back-edge), re-verifying
  `lint-imports` + `tach check`. It must **not** be bundled into this CI-config
  matrix-entry commit.
- Standard pylint/pytest/mypy via MCP tools — green.

## LLM prompt
> Read `pr_info/steps/summary.md` and `pr_info/steps/step_4.md`. Add the `pycycle`
> matrix entry to the `architecture` job in `.github/workflows/ci.yml`. Run pycycle
> locally with the exact `--ignore` list and confirm no cycles are found (a local run
> already confirmed none). This commit is the single matrix line only — no `src/`
> edits. In the unlikely event a cycle is reported, do NOT fix it here: land the fix
> as a separate, earlier commit and re-verify import-linter and tach. Run the
> standard MCP quality checks. Commit as one change.
