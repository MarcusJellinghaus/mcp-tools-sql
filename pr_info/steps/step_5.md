# Step 5 — Broaden ruff command scope (string-fidelity, no-op)

See `pr_info/steps/summary.md` (item 5). One commit.

## WHERE
- Modify `.github/workflows/ci.yml` → `test` job, `ruff-docstrings` matrix entry

## WHAT
One-line change:

```diff
-          - {name: "ruff-docstrings", cmd: "ruff version && ruff check src"}
+          - {name: "ruff-docstrings", cmd: "ruff version && ruff check src tests"}
```

**Behavioral no-op:** the `"tests/**/*.py" = ["D","DOC"]` per-file-ignore in
`[tool.ruff.lint.per-file-ignores]` stays, so ruff still checks nothing in `tests`.
The change exists purely for command-string fidelity with `mcp_coder`'s `ci.yml` and
is forward-compatible if that ignore is ever narrowed.

**Do NOT** remove or modify the `tests/**/*.py` per-file-ignore.

## HOW
Edit only the one `cmd` string. No `pyproject.toml` change.

## ALGORITHM
N/A.

## DATA
None.

## Verification (the "test" for this step)
- `ruff check src tests` exits `0` (identical result to `ruff check src` while the
  tests ignore is in place).
- Standard pylint/pytest/mypy via MCP tools — green.

## LLM prompt
> Read `pr_info/steps/summary.md` and `pr_info/steps/step_5.md`. Change the
> `ruff-docstrings` matrix command in `.github/workflows/ci.yml` from
> `ruff check src` to `ruff check src tests`. Do not touch the `tests/**/*.py`
> per-file-ignore in `pyproject.toml`. Confirm `ruff check src tests` exits 0. Run
> the standard MCP quality checks. Commit as one change.
