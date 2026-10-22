# Step 6 — Enable `S` (flake8-bandit)

## LLM prompt
> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_6.md`.
> Run the checks listed below, format, and make exactly one commit.

## WHERE
- `pyproject.toml`
- `src/mcp_tools_sql/summarize/sql.py` (~line 202, `probe = f"SELECT 1 FROM ..."`)
- `src/mcp_tools_sql/update_tools.py` (`sql = f"UPDATE {qualified} SET ..."` in `body`)
- `src/mcp_tools_sql/verification/connection.py` (~line 102, `["klist", "-s"]`)

## WHAT
1. `pyproject.toml`
   - `select` gets `"S"` after `"C4", "B",`.
   - Tests per-file ignore becomes
     `["D", "DOC", "SIM117", "S101", "S105", "S106", "S108", "S608"]`
     with the comment block from the summary (assert idiom; fake credentials
     and `/tmp` literals; SQL fixtures built on purpose).
   - No `S` code in the global `ignore`. No `S404`/`S603`.
2. Inline suppressions in src, each with a one-line reason on the flagged line:
   - `summarize/sql.py`:
     `# noqa: S608 - probe is vetted by basic_preflight and arbitrary_sql_violation; only its parsed AST is used`
   - `update_tools.py`:
     `# noqa: S608 - table, column and key names come from validated config; values are bound :name params`
   - `connection.py`, on the `["klist", "-s"],` line:
     `# noqa: S607 - klist is resolved via PATH on purpose`

## HOW
The noqa must sit on the line ruff reports. If black moves a comment off that
line, re-run `run_ruff_check` and move it back to the reported line.

## Verification
- `run_ruff_check(target_directories=["src","tests","tools"])` → clean.
- `run_ruff_check(select=["S"], target_directories=["src"])` → clean (src
  needs only the three inline noqa comments).
- If any `S` finding remains in src that is not one of the three sites above
  (e.g. `S101` left from steps 4–5), write one line to `pr_info/.blocked.txt`
  naming the file:line and code, and stop.
- pylint, mypy, pytest green.

## Commit
`ruff: enable S with tests carve-out and justified src noqa`
