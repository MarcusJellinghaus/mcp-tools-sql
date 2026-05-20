# Step 8 — Move `verify_updates` + `verify_one_update` + helpers

**Goal:** Move `verify_updates()`, `verify_one_update()`, and
`_list_table_columns` from `cli/commands/verify.py` to
`verification/updates.py`. Move tests. **Carry forward the two NOTE
comments verbatim** — they guard load-bearing dict insertion order.

## WHERE

### New files
- `src/mcp_tools_sql/verification/updates.py`
- `tests/verification/test_updates.py`

### Modified files
- `src/mcp_tools_sql/cli/commands/verify.py` — remove all of the above
- `src/mcp_tools_sql/verification/__init__.py` — re-export `verify_updates`
  (NOT `verify_one_update` — that stays submodule-internal)
- `tests/cli/test_verify.py` — delete the updates tests

## WHERE — load-bearing constraint

Dict insertion order in `verify_one_update` is asserted byte-equal by the
CLI snapshot regression test. Two NOTE comments in the existing code
explicitly warn against refactoring to dict comprehensions or `dict()`
constructors:

```python
# NOTE: Key insertion order is load-bearing — the CLI snapshot test and
# verify_queries/verify_updates assert byte-equality against this order.
# Do not refactor to dict comprehensions or dict() constructors.
```

**These comments must travel verbatim with the function.** `move_symbol`
preserves them.

## WHAT

### `verification/updates.py`

```python
"""Updates section: table exists, key column exists, fields exist."""
from __future__ import annotations

from typing import Any

from mcp_tools_sql.backends.base import DatabaseBackend
from mcp_tools_sql.config.models import UpdateConfig
from mcp_tools_sql.identifiers import IDENTIFIER_PATTERN, identifier_error
from mcp_tools_sql.verification._helpers import _entry


def _list_table_columns(
    backend: DatabaseBackend,
    backend_name: str,
    schema: str,
    table: str,
) -> list[str] | None:
    """Return column names for ``table`` in ``schema``, or ``None`` if missing."""
    # ... body moved verbatim ...


def verify_one_update(
    name: str,
    ucfg: UpdateConfig,
    backend_name: str,
    backend: DatabaseBackend,
) -> dict[str, Any]:
    """Per-entry validation for a single update.

    NOTE: Key insertion order is load-bearing ...
    """
    # ... body moved verbatim, including the two NOTE comments ...


def verify_updates(
    updates: dict[str, UpdateConfig],
    backend_name: str,
    backend: DatabaseBackend,
) -> dict[str, Any]:
    """Per-update validation: table exists, key column exists, fields exist."""
    # ... body moved verbatim ...
```

### `verification/__init__.py` (extended)

```python
from mcp_tools_sql.verification.updates import verify_updates

__all__ = [
    ...,
    "verify_updates",
]
# verify_one_update is intentionally NOT re-exported.
```

### `tests/verification/test_updates.py`

Move tests from `tests/cli/test_verify.py` (lines ~812–914 + ~975–1075 +
~1176–1197 + ~1290–1336), updating imports:

```python
from mcp_tools_sql.verification import verify_updates
from mcp_tools_sql.verification.updates import verify_one_update
```

Tests moved:
- `test_verify_updates_valid_sqlite`
- `test_verify_updates_detects_missing_table`
- `test_verify_updates_detects_missing_key_column`
- `test_verify_updates_detects_missing_field_column`
- `test_verify_updates_no_updates_configured`
- `test_verify_updates_rejects_invalid_table_identifier`
- `test_verify_updates_rejects_invalid_schema_identifier`
- `test_verify_updates_rejects_invalid_key_field_identifier`
- `test_verify_updates_rejects_invalid_field_identifier`
- `test_verify_updates_surfaces_required_flag_inline`
- `test_verify_one_update_matches_bulk` (parametrized)

## HOW

### Recommended tool

```
move_symbol(
    source_file="src/mcp_tools_sql/cli/commands/verify.py",
    symbol_names=["_list_table_columns", "verify_one_update", "verify_updates"],
    dest_file="src/mcp_tools_sql/verification/updates.py",
)
```

Then manually:
1. Add the imports at the top (including `identifiers`).
2. Re-export `verify_updates` from `verification/__init__.py`.
3. Move the tests.
4. **Read the new `verification/updates.py` and confirm both NOTE
   comments are present in `verify_one_update`.**

### Integration in `cli/commands/verify.py`

Add to the top-level import block:

```python
from mcp_tools_sql.verification import verify_updates
```

`run()` continues to call `verify_updates(query_config.updates,
connection.backend, open_backend)` unchanged.

## ALGORITHM

No algorithm — functions moved verbatim. The branches in `verify_one_update`
that govern dict-key insertion order (bad identifier → 1 row; missing
table → 3 rows; happy → 3 rows) must be preserved exactly.

## DATA

- `verify_one_update` returns a dict with 1 or 3 entries depending on
  branch:
  - bad-identifier: `<name>.table` only.
  - missing-table: `<name>.table`, `<name>.key_column`, `<name>.fields`.
  - happy: `<name>.table`, `<name>.key_column`, `<name>.fields`.
- **Insertion order is load-bearing.**

## Checks

Run after edits:
- `mcp__mcp-tools-py__run_pylint_check`
- `mcp__mcp-tools-py__run_mypy_check`
- `mcp__mcp-tools-py__run_pytest_check(extra_args=["-n", "auto", "-m", "not git_integration and not claude_cli_integration and not claude_api_integration and not formatter_integration and not github_integration and not langchain_integration"])`
- `mcp__mcp-tools-py__run_tach_check`
- `mcp__mcp-tools-py__run_lint_imports_check`

All must pass. **Explicitly re-run the snapshot test:**

```
mcp__mcp-tools-py__run_pytest_check(extra_args=[
    "tests/cli/test_verify.py::test_verify_cli_queries_updates_snapshot", "-v"
])
```

## LLM Prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_8.md`. Implement
> step 8: move `_list_table_columns`, `verify_one_update`, and
> `verify_updates` from `cli/commands/verify.py` to a new file
> `src/mcp_tools_sql/verification/updates.py`. Use the `move_symbol` MCP
> tool. **Re-export only `verify_updates` from `verification/__init__.py`**
> (verify_one_update stays submodule-internal). After the move, read the
> new file and confirm both NOTE comments in `verify_one_update` warning
> against dict-comprehension refactors are still present verbatim — they
> guard the byte-exact CLI snapshot. Move the eleven updates-related
> tests from `tests/cli/test_verify.py` to
> `tests/verification/test_updates.py`. The per-entry equality test
> imports `verify_one_update` from `mcp_tools_sql.verification.updates`
> directly. Do not refactor any function body. Run all checks; explicitly
> re-run the snapshot test. All must pass before committing.
