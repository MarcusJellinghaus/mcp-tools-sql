# Step 10 — Unpin `mcp-coder-utils`

## LLM prompt
Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_10.md`.
Run pylint, mypy, pytest (`-n auto`). One commit.

## Decision
`mcp-coder-utils` is consumed from GitHub main, not from PyPI releases. The version floor is
dropped instead of bumped, so this step does not wait for a release containing
`mcp_coder_utils.tool_spec`.

## WHERE
- `pyproject.toml`, `[project] dependencies`
- `tests/cli/test_main_dispatch.py` — docstring that cited the old floor

## WHAT
`"mcp-coder-utils>=0.1.6"` → `"mcp-coder-utils"`, with a comment pointing at the GitHub sources.
Leave `[tool.uv.sources]` and `[tool.mcp-coder.install-from-github]` unchanged; they already
point at `git+https://github.com/MarcusJellinghaus/mcp-coder-utils.git`.

## Tests
None new; the existing suite (incl. `tests/test_tool_spec_shim.py` and
`test_upstream_setup_logging_accepts_console_level`) must pass.
