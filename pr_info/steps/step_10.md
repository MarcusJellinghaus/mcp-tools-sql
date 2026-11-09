# Step 10 — Bump the `mcp-coder-utils` pin

## LLM prompt
Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_10.md`.
Run pylint, mypy, pytest (`-n auto`). One commit.

## Precondition
A released `mcp-coder-utils` version that contains `mcp_coder_utils.tool_spec` must exist on PyPI.
Check the `mcp-coder-utils` reference project's tags (`git` tool, `ls_remote --tags` or `log --tags`
with `reference_name="mcp-coder-utils"`) for a tag newer than `0.1.6` whose tree contains
`src/mcp_coder_utils/tool_spec.py`. If there is none, write one line to `pr_info/.blocked.txt` and stop.

## WHERE
- `pyproject.toml`, `[project] dependencies`

## WHAT
`"mcp-coder-utils>=0.1.6"` → `"mcp-coder-utils>=<released version>"` (likely `0.1.7`).
Leave `[tool.uv.sources]` and the git dependency used for dev installs unchanged.

## Tests
None new; the existing suite (incl. `tests/test_tool_spec_shim.py`) must pass.
