# Step 1 — Gate preview rules

## LLM prompt
> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_1.md`.
> Change only `pyproject.toml`. Run the checks listed below, format, and make
> exactly one commit.

## WHERE
- `pyproject.toml`, section `[tool.ruff.lint]`

## WHAT
`preview = true` is already set, so every preview-only rule in any selected
group fires. Gate them before any new group is added (otherwise `UP052` and
`S404` leak into later steps).

1. Add `explicit-preview-rules = true` right after `preview = true`, with the
   comment `# preview rules fire only when selected by exact code`.
2. In `select`, replace `"DOC"` with the exact codes
   `"DOC201", "DOC202", "DOC402", "DOC403", "DOC501", "DOC502"`, preceded by
   the two-line comment from the summary ("DOC rules are preview-only; …").
3. Delete the stale comment `# Only enable docstring rules for now`. Keep
   `# preview needed for DOC rules (pydoclint)`.
4. Leave `ignore` and `per-file-ignores` (`"tests/**/*.py" = ["D", "DOC"]`)
   unchanged.

## HOW
Config only; no code or tests change.

## DATA
Resulting `select = ["D", "DOC201", "DOC202", "DOC402", "DOC403", "DOC501", "DOC502"]`.

## Verification
- `run_ruff_check(target_directories=["src","tests"])` → clean.
- Prove the DOC rules still enforce: `run_ruff_check(select=["DOC501"],
  target_directories=["src"])` → clean (no error about unknown/empty selection).
- If either check reports findings, write one line to `pr_info/.blocked.txt`
  and stop.
- pylint, mypy and pytest unchanged and green.

## Commit
`ruff: gate preview rules behind explicit-preview-rules`
