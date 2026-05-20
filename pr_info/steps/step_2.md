# Step 2 — Move `verify_environment`

**Goal:** Move `verify_environment()` from `cli/commands/verify.py` to
`verification/environment.py`. Move its tests to
`tests/verification/test_environment.py`.

## WHERE

### New files
- `src/mcp_tools_sql/verification/environment.py`
- `tests/verification/test_environment.py`

### Modified files
- `src/mcp_tools_sql/cli/commands/verify.py` — remove `verify_environment`
  definition; in `run()`, replace local call with import from
  `mcp_tools_sql.verification`
- `src/mcp_tools_sql/verification/__init__.py` — re-export `verify_environment`
- `tests/cli/test_verify.py` — delete the two `verify_environment` tests
  (they move to the new file)

## WHAT

### `verification/environment.py`

```python
"""Environment section: Python version, virtualenv, key package versions."""
from __future__ import annotations

import importlib.metadata
import sys
from typing import Any

from mcp_tools_sql.verification._helpers import _entry


def verify_environment() -> dict[str, Any]:
    """Report Python version, virtualenv status, and key package versions.

    Returns:
        Verifier result dict with entries for ``python_version``,
        ``virtualenv``, ``mcp_tools_sql``, ``mcp_coder_utils`` and an
        ``overall_ok`` flag.
    """
    # ... body moved verbatim from cli/commands/verify.py ...
```

### `verification/__init__.py` (extended)

```python
from mcp_tools_sql.verification._helpers import VerifierEntry
from mcp_tools_sql.verification.environment import verify_environment

__all__ = ["VerifierEntry", "verify_environment"]
```

### `tests/verification/test_environment.py`

Move both tests verbatim from `tests/cli/test_verify.py` (lines ~66–83),
updating the import:

```python
from mcp_tools_sql.verification import verify_environment
```

Tests moved:
- `test_verify_environment_returns_python_version`
- `test_verify_environment_overall_ok_true_when_packages_present`

## HOW

### Recommended tool

Use `mcp__mcp-tools-py__move_symbol` to relocate `verify_environment`:

```
move_symbol(
    source_file="src/mcp_tools_sql/cli/commands/verify.py",
    symbol_names=["verify_environment"],
    dest_file="src/mcp_tools_sql/verification/environment.py",
)
```

This updates all project-wide imports automatically. Then manually:
1. Add the `_entry` import at the top of `environment.py`.
2. Re-export from `verification/__init__.py`.
3. Move the two tests by editing `tests/cli/test_verify.py` and creating
   `tests/verification/test_environment.py`.
4. Verify `cli/commands/verify.py`'s `run()` still calls `verify_environment`
   via the new import path (the move_symbol tool handles this).

### Integration in `cli/commands/verify.py`

After the move, the top-level import block adds:

```python
from mcp_tools_sql.verification import verify_environment
```

And `run()` continues to call `verify_environment()` unchanged.

## ALGORITHM

No algorithm — function is moved verbatim.

## DATA

- Return type: `dict[str, Any]` (unchanged).
- Entry keys: `python_version`, `virtualenv`, `mcp_tools_sql`,
  `mcp_coder_utils`, `overall_ok`.

## Checks

Run after edits:
- `mcp__mcp-tools-py__run_pylint_check`
- `mcp__mcp-tools-py__run_mypy_check`
- `mcp__mcp-tools-py__run_pytest_check(extra_args=["-n", "auto", "-m", "not git_integration and not claude_cli_integration and not claude_api_integration and not formatter_integration and not github_integration and not langchain_integration"])`
- `mcp__mcp-tools-py__run_tach_check`
- `mcp__mcp-tools-py__run_lint_imports_check`

All must pass.

## LLM Prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_2.md`. Implement
> step 2: move `verify_environment` from `cli/commands/verify.py` to a new
> file `src/mcp_tools_sql/verification/environment.py`. Use the
> `move_symbol` MCP tool for the source move. Re-export the function from
> `verification/__init__.py`. Move the two existing tests
> (`test_verify_environment_returns_python_version` and
> `test_verify_environment_overall_ok_true_when_packages_present`) from
> `tests/cli/test_verify.py` to a new `tests/verification/test_environment.py`,
> updating the import to `from mcp_tools_sql.verification import
> verify_environment`. Do not modify `verify_environment`'s body. Run
> pylint, mypy, pytest (with the standard exclusion markers), tach, and
> lint-imports; all must pass before committing.
