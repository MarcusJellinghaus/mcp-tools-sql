# Step 5 — Move `verify_builtin`

**Goal:** Move `verify_builtin()` from `cli/commands/verify.py` to
`verification/builtin.py`. Move its tests.

## WHERE

### New files
- `src/mcp_tools_sql/verification/builtin.py`
- `tests/verification/test_builtin.py`

### Modified files
- `src/mcp_tools_sql/cli/commands/verify.py` — remove `verify_builtin`
- `src/mcp_tools_sql/verification/__init__.py` — re-export `verify_builtin`
- `tests/cli/test_verify.py` — delete the two builtin tests

## WHAT

### `verification/builtin.py`

```python
"""Builtin section: default queries + tools registered count."""
from __future__ import annotations

from typing import Any

from mcp_tools_sql.schema_tools import load_default_queries
from mcp_tools_sql.verification._helpers import make_entry


def verify_builtin() -> dict[str, Any]:
    """Report status of built-in default queries."""
    # ... body moved verbatim ...
```

This is the first verification submodule that imports from `schema_tools`.
The `.importlinter` placement set up in step 1 (verification above
schema_tools) is what makes this import legal.

### `verification/__init__.py` (extended)

```python
from mcp_tools_sql.verification.builtin import verify_builtin

__all__ = [
    "VerifierEntry",
    "verify_environment",
    "verify_config_files",
    "verify_dependencies",
    "verify_builtin",
]
```

### `tests/verification/test_builtin.py`

Move both tests verbatim from `tests/cli/test_verify.py` (lines ~262–278),
updating the import:

```python
from mcp_tools_sql.verification import verify_builtin
```

Tests moved:
- `test_verify_builtin_returns_query_count`
- `test_verify_reports_default_queries_count`

## HOW

### Recommended tool

```
move_symbol(
    source_file="src/mcp_tools_sql/cli/commands/verify.py",
    symbol_names=["verify_builtin"],
    dest_file="src/mcp_tools_sql/verification/builtin.py",
)
```

Then manually:
1. Add the `make_entry` and `load_default_queries` imports at the top (and
   update every `_entry(...)` call in the moved body to `make_entry(...)`).
2. Re-export from `verification/__init__.py`.
3. Move the two tests.

### Integration in `cli/commands/verify.py`

Add to the top-level import block:

```python
from mcp_tools_sql.verification import verify_builtin
```

`run()` continues to call `verify_builtin()` unchanged.

## ALGORITHM

No algorithm — function is moved verbatim.

## DATA

- Return type: `dict[str, Any]` (unchanged).
- Entry keys: `default_queries_loaded`, `tools_registered_count`, `overall_ok`.

## Checks

Run after edits:
- `mcp__mcp-tools-py__run_pylint_check`
- `mcp__mcp-tools-py__run_mypy_check`
- `mcp__mcp-tools-py__run_pytest_check(extra_args=["-n", "auto", "-m", "not git_integration and not claude_cli_integration and not claude_api_integration and not formatter_integration and not github_integration and not langchain_integration"])`
- `mcp__mcp-tools-py__run_tach_check`
- `mcp__mcp-tools-py__run_lint_imports_check`

All must pass — in particular, `lint-imports` must confirm that
`verification.builtin` importing from `schema_tools` is permitted by the
layer ordering established in step 1.

## LLM Prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_5.md`. Implement
> step 5: move `verify_builtin` from `cli/commands/verify.py` to a new
> file `src/mcp_tools_sql/verification/builtin.py`. Use the `move_symbol`
> MCP tool. Re-export from `verification/__init__.py`. Move the two
> existing tests (`test_verify_builtin_returns_query_count`,
> `test_verify_reports_default_queries_count`) from `tests/cli/test_verify.py`
> to a new `tests/verification/test_builtin.py`. Update test imports to
> `from mcp_tools_sql.verification import verify_builtin`. After running
> lint-imports, confirm there is no layer violation for the new
> `verification → schema_tools` import (this is what the step-1 layer
> ordering is for). Do not modify the function body. Run all checks; all
> must pass before committing.
