# Step 1 — `utils/tool_spec.py` shim

## LLM prompt
Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_1.md`.
Follow TDD: write the test first, then the shim. Run pylint, mypy and pytest
(`-n auto`) and make them pass. One commit.

## Precondition
`mcp_coder_utils.tool_spec` must be importable in the project environment
(installed from git main via `[tool.uv.sources]`). Check with
`get_library_source("mcp_coder_utils.tool_spec.tool_spec")`. If it is not
importable, write one line to `pr_info/.blocked.txt` and stop.

## WHERE
- Create `src/mcp_tools_sql/utils/tool_spec.py`
- Create `tests/test_tool_spec_shim.py`
- Modify `.claude/CLAUDE.md` (Shared Libraries section)

## WHAT
```python
"""Tool contract — thin shim over mcp-coder-utils."""
from mcp_coder_utils.tool_spec import ToolCollector, ToolSink, ToolSpec, tool_spec

__all__ = ["ToolSpec", "tool_spec", "ToolSink", "ToolCollector"]
```
Same shape as `utils/user_app_data.py`.

## HOW
- `.claude/CLAUDE.md`: Shared Libraries sentence becomes
  "`log_utils`, `user_app_data`, `subprocess_runner` and `tool_spec` in `src/mcp_tools_sql/utils/` are thin shims …".
- The `mcp_coder_utils_isolation` contract already allows `utils.** -> mcp_coder_utils`.

## Tests (`tests/test_tool_spec_shim.py`)
- The four names are importable from `mcp_tools_sql.utils.tool_spec` and are the same objects as in `mcp_coder_utils.tool_spec`. Tests may import `mcp_coder_utils` directly; the isolation contract only covers `mcp_tools_sql`.
- `tool_spec` on a small async function with an `Annotated[int, Field(ge=1)]` parameter returns a spec with the expected `name`, `group`, `read_only`; `ToolCollector` raises `ValueError` on a duplicate name.

## DATA
No new data structures; re-exports only.
