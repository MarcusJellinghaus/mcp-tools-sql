# Step 2 — Add the rule groups that are already clean

## LLM prompt
> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_2.md`.
> Change only `pyproject.toml`. Run the checks listed below, format, and make
> exactly one commit.

## WHERE
- `pyproject.toml`, `[tool.ruff.lint]` and `[tool.ruff.lint.per-file-ignores]`

## WHAT
1. Extend `select` (order as in the summary's final shape):
   `"ANN"`, `"SIM"`, `"SIM905"` (with comment "SIM905 is preview-only; see
   explicit-preview-rules note above."), `"E"`, `"F"`, `"C4"`, `"PLW1510"`
   (with comment "PLW1510 only: the PL prefix would re-enable pylint's
   disabled R category (PLR09xx).").
2. Extend `ignore`:
   - `"ANN401",  # Any is correct at library/CLI boundaries; mypy strict covers the rest`
   - `"E501",  # line length is owned by the formatter (black); not re-checked here`
3. Tests per-file ignore becomes `["D", "DOC", "SIM117"]`.
4. Add the rejection note under `# preview needed for DOC rules (pydoclint)`:
   `# TRY, EM, PL (except PLW1510) rejected — see mcp_coder #1172, #1181.`

## HOW
Config only. TDD does not apply (no behaviour change).

## Verification
- `run_ruff_check(target_directories=["src","tests","tools"])` → clean.
- If it reports any finding, write one line to `pr_info/.blocked.txt` and
  stop (the issue measured these groups as clean; a finding means the
  baseline moved).
- pylint, mypy, pytest green.

## Commit
`ruff: enable F, E, C4, ANN, SIM, SIM905, PLW1510`
