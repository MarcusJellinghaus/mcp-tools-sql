# Step 3 — File-size guard + `.large-files-allowlist`

See `pr_info/steps/summary.md` (item 3). One commit.

## WHERE
- Create `.large-files-allowlist` (repo root)
- Modify `.github/workflows/ci.yml` → `test` job `matrix.check`

## WHAT
Create `.large-files-allowlist` — non-empty on creation (`mcp-tools-sql.md` is 1053
lines, the only tracked file over 750). Minimal repo-specific header (do NOT copy
`mcp_coder`'s header with its `#353` / `--generate-allowlist` cruft):

```
# Files exceeding the 750-line limit, grandfathered in.
# Reduce over time; do not add new entries.
mcp-tools-sql.md
```

## HOW
Add this matrix entry to the **`test`** job's `matrix.check` list:

```yaml
          - {name: "file-size", cmd: "mcp-coder check file-size --max-lines 750 --allowlist-file .large-files-allowlist"}
```

`mcp-coder` is already a `dev` dep (kept in step 1), so `.[dev]` provides the CLI —
no `uvx`, no separate job.

## ALGORITHM
N/A — config file + one matrix line.

## DATA
Allowlist = newline-delimited file paths; `#` lines are comments.

## Verification (the "test" for this step)
- `mcp-coder check file-size --max-lines 750 --allowlist-file .large-files-allowlist`
  exits `0` (the one over-limit file is allowlisted; nothing else trips it).
- Standard pylint/pytest/mypy via MCP tools — green.

## LLM prompt
> Read `pr_info/steps/summary.md` and `pr_info/steps/step_3.md`. Create
> `.large-files-allowlist` with the minimal two-line header and the single entry
> `mcp-tools-sql.md`. Add the `file-size` matrix entry to the `test` job in
> `.github/workflows/ci.yml`. Run the file-size command and confirm it exits 0. Run
> the standard MCP quality checks. Commit as one change.
