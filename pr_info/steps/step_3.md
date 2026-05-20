# Step 3 — Move `verify_config_files`

**Goal:** Move `verify_config_files()` from `cli/commands/verify.py` to
`verification/config_files.py`. Move its tests.

## WHERE

### New files
- `src/mcp_tools_sql/verification/config_files.py`
- `tests/verification/test_config_files.py`

### Modified files
- `src/mcp_tools_sql/cli/commands/verify.py` — remove `verify_config_files`
- `src/mcp_tools_sql/verification/__init__.py` — re-export
  `verify_config_files`
- `tests/cli/test_verify.py` — delete the two `verify_config_files` tests

## WHAT

### `verification/config_files.py`

```python
"""Config files section: query config + database config resolution and parse."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp_tools_sql.config.loader import (
    _has_sensitive_keys,
    _read_toml,
    discover_query_config,
    load_database_config,
    load_query_config,
)
from mcp_tools_sql.verification._helpers import _entry


def verify_config_files(
    config_path: Path | None,
    db_config_path: Path | None,
) -> dict[str, Any]:
    """Verify that both config files resolve to a path and parse cleanly."""
    # ... body moved verbatim from cli/commands/verify.py ...
```

### `verification/__init__.py` (extended)

```python
from mcp_tools_sql.verification.config_files import verify_config_files

__all__ = ["VerifierEntry", "verify_environment", "verify_config_files"]
```

### `tests/verification/test_config_files.py`

Move both tests verbatim from `tests/cli/test_verify.py` (lines ~91–115),
updating the import:

```python
from mcp_tools_sql.verification import verify_config_files
```

Also move/duplicate the `valid_query_config` and `valid_database_config`
fixtures used by these tests (currently in `tests/cli/test_verify.py`
lines ~38–58). Decision: **inline both fixtures in
`tests/verification/test_config_files.py`** since they are only used by
config-file tests, not by the rest of the verification tests. The CLI
test file keeps its copies because the remaining CLI-level integration
tests still use them.

Tests moved:
- `test_verify_config_files_missing_returns_err`
- `test_verify_config_files_valid_returns_ok`

## HOW

### Recommended tool

```
move_symbol(
    source_file="src/mcp_tools_sql/cli/commands/verify.py",
    symbol_names=["verify_config_files"],
    dest_file="src/mcp_tools_sql/verification/config_files.py",
)
```

Then manually:
1. Add the `_entry` and `mcp_tools_sql.config.loader` imports at the top.
2. Re-export from `verification/__init__.py`.
3. Move the two tests and the helper fixtures.

### Integration in `cli/commands/verify.py`

Add to the top-level import block:

```python
from mcp_tools_sql.verification import verify_config_files
```

`run()` continues to call `verify_config_files(args.config, args.database_config)`
unchanged.

## ALGORITHM

No algorithm — function is moved verbatim.

## DATA

- Return type: `dict[str, Any]` (unchanged).
- Entry keys (depending on what resolves):
  `query_config_path`, `query_config_parse`, `query_config_sensitive_keys`
  (only when sensitive keys found; has `warn=True` flag),
  `database_config_path`, `database_config_parse`, `overall_ok`.

## Checks

Run after edits:
- `mcp__mcp-tools-py__run_pylint_check`
- `mcp__mcp-tools-py__run_mypy_check`
- `mcp__mcp-tools-py__run_pytest_check(extra_args=["-n", "auto", "-m", "not git_integration and not claude_cli_integration and not claude_api_integration and not formatter_integration and not github_integration and not langchain_integration"])`
- `mcp__mcp-tools-py__run_tach_check`
- `mcp__mcp-tools-py__run_lint_imports_check`

All must pass.

## LLM Prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_3.md`. Implement
> step 3: move `verify_config_files` from `cli/commands/verify.py` to a new
> file `src/mcp_tools_sql/verification/config_files.py`. Use the
> `move_symbol` MCP tool. Re-export from `verification/__init__.py`. Move
> the two existing tests (`test_verify_config_files_missing_returns_err`,
> `test_verify_config_files_valid_returns_ok`) from `tests/cli/test_verify.py`
> to a new `tests/verification/test_config_files.py`. Duplicate the
> `valid_query_config` and `valid_database_config` fixtures inline in the
> new test file (the CLI test file keeps its own copies). Update test
> imports to `from mcp_tools_sql.verification import verify_config_files`.
> Do not modify the function body. Run all checks; all must pass before
> committing.
