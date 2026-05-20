# Step 4 — Move `verify_dependencies`

**Goal:** Move `verify_dependencies()` and its two private helpers
(`_verify_dependencies_mssql`, `_verify_dependencies_postgresql`) from
`cli/commands/verify.py` to `verification/dependencies.py`. Move its tests.

## WHERE

### New files
- `src/mcp_tools_sql/verification/dependencies.py`
- `tests/verification/test_dependencies.py`

### Modified files
- `src/mcp_tools_sql/cli/commands/verify.py` — remove `verify_dependencies`,
  `_verify_dependencies_mssql`, `_verify_dependencies_postgresql`
- `src/mcp_tools_sql/verification/__init__.py` — re-export
  `verify_dependencies`
- `tests/cli/test_verify.py` — delete the six dependency-related tests

## WHAT

### `verification/dependencies.py`

```python
"""Dependencies section: backend-conditional optional/extra deps check."""
from __future__ import annotations

from typing import Any

from mcp_tools_sql.verification._helpers import make_entry


def verify_dependencies(backend: str) -> dict[str, Any]:
    """Backend-conditional check of optional/extra dependencies."""
    # ... body moved verbatim ...


def _verify_dependencies_mssql() -> dict[str, Any]:
    """Check for ``pyodbc`` and a ``SQL Server`` ODBC driver."""
    # ... body moved verbatim ...


def _verify_dependencies_postgresql() -> dict[str, Any]:
    """Check for the ``psycopg`` package."""
    # ... body moved verbatim ...
```

### `verification/__init__.py` (extended)

```python
from mcp_tools_sql.verification.dependencies import verify_dependencies

__all__ = [
    "VerifierEntry",
    "verify_environment",
    "verify_config_files",
    "verify_dependencies",
]
```

### `tests/verification/test_dependencies.py`

Move all six tests verbatim from `tests/cli/test_verify.py` (lines ~187–254),
updating the import:

```python
from mcp_tools_sql.verification import verify_dependencies
```

Tests moved:
- `test_verify_dependencies_sqlite_shows_info_line`
- `test_verify_dependencies_unknown_backend_returns_err`
- `test_verify_dependencies_postgresql_when_psycopg_missing`
- `test_verify_dependencies_mssql_when_pyodbc_missing`
- `test_verify_dependencies_mssql_with_pyodbc_and_driver`
- `test_verify_dependencies_mssql_with_pyodbc_no_driver`

## HOW

### Recommended tool

```
move_symbol(
    source_file="src/mcp_tools_sql/cli/commands/verify.py",
    symbol_names=[
        "verify_dependencies",
        "_verify_dependencies_mssql",
        "_verify_dependencies_postgresql",
    ],
    dest_file="src/mcp_tools_sql/verification/dependencies.py",
)
```

Then manually:
1. Add the `make_entry` import at the top (and update every `_entry(...)`
   call in the moved bodies to `make_entry(...)`).
2. Re-export `verify_dependencies` from `verification/__init__.py`.
3. Move the six tests.

### Integration in `cli/commands/verify.py`

Add to the top-level import block:

```python
from mcp_tools_sql.verification import verify_dependencies
```

`run()` continues to call `verify_dependencies(backend)` unchanged.

## ALGORITHM

No algorithm — functions are moved verbatim.

## DATA

- Return type: `dict[str, Any]` (unchanged).
- For sqlite: `{info, overall_ok}`.
- For unknown: `{backend, overall_ok}`.
- For mssql: `{pyodbc, odbc_driver, overall_ok}`.
- For postgresql: `{psycopg, overall_ok}`.

## Checks

Run after edits:
- `mcp__mcp-tools-py__run_pylint_check`
- `mcp__mcp-tools-py__run_mypy_check`
- `mcp__mcp-tools-py__run_pytest_check(extra_args=["-n", "auto", "-m", "not git_integration and not claude_cli_integration and not claude_api_integration and not formatter_integration and not github_integration and not langchain_integration"])`
- `mcp__mcp-tools-py__run_tach_check`
- `mcp__mcp-tools-py__run_lint_imports_check`

All must pass.

## LLM Prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_4.md`. Implement
> step 4: move `verify_dependencies`, `_verify_dependencies_mssql`, and
> `_verify_dependencies_postgresql` from `cli/commands/verify.py` to a new
> file `src/mcp_tools_sql/verification/dependencies.py`. Use the
> `move_symbol` MCP tool to relocate all three symbols in one call.
> Re-export `verify_dependencies` (only the public one) from
> `verification/__init__.py`. Move the six existing dependency tests from
> `tests/cli/test_verify.py` to a new
> `tests/verification/test_dependencies.py`. Update test imports to
> `from mcp_tools_sql.verification import verify_dependencies`. Do not
> modify function bodies. Run all checks; all must pass before committing.
