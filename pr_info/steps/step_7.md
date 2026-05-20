# Step 7 — Move `verify_queries` + `verify_one_query` + helpers

**Goal:** Move `verify_queries()`, `verify_one_query()`, `_check_sql_explain`,
`_check_params_well_formed`, `_VALID_PARAM_TYPES`, and `_DUMMY_BY_TYPE`
from `cli/commands/verify.py` to `verification/queries.py`. Move tests.

## WHERE

### New files
- `src/mcp_tools_sql/verification/queries.py`
- `tests/verification/test_queries.py`

### Modified files
- `src/mcp_tools_sql/cli/commands/verify.py` — remove all of the above
- `src/mcp_tools_sql/verification/__init__.py` — re-export `verify_queries`
  (NOT `verify_one_query` — that stays submodule-internal per the issue)
- `tests/cli/test_verify.py` — delete the queries tests

## WHERE — load-bearing constraint

Dict insertion order in `verify_one_query` is asserted byte-equal by the CLI
snapshot regression test (`test_verify_cli_queries_updates_snapshot`).
**Use `move_symbol` to relocate verbatim. Do not refactor or reorder any
dict-key assignment.**

## WHAT

### `verification/queries.py`

```python
"""Queries section: SQL EXPLAIN, params well-formed, max_rows_default > 0."""
from __future__ import annotations

import datetime
from typing import Any

from mcp_tools_sql.backends.base import DatabaseBackend
from mcp_tools_sql.config.models import QueryConfig, QueryParamConfig
from mcp_tools_sql.query_helpers import extract_sql_params
from mcp_tools_sql.verification._helpers import make_entry


_VALID_PARAM_TYPES = {"str", "int", "float", "datetime"}
_DUMMY_BY_TYPE: dict[str, Any] = {
    "str": "",
    "int": 0,
    "float": 0.0,
    "datetime": datetime.datetime(2000, 1, 1),
}


def _check_sql_explain(
    sql: str,
    params: dict[str, QueryParamConfig],
    backend_name: str,
    backend: DatabaseBackend,
) -> tuple[bool, str]:
    """Return ``(ok, error_message)`` for a single query's SQL."""
    # ... body moved verbatim ...


def _check_params_well_formed(
    sql: str, params: dict[str, QueryParamConfig]
) -> tuple[bool, str]:
    """Verify ``:name`` placeholders in SQL match config params + types."""
    # ... body moved verbatim ...


def verify_one_query(
    name: str,
    qcfg: QueryConfig,
    backend_name: str,
    backend: DatabaseBackend,
) -> dict[str, Any]:
    """Per-entry validation for a single query."""
    # ... body moved verbatim — dict-insertion order matters ...


def verify_queries(
    queries: dict[str, QueryConfig],
    backend_name: str,
    backend: DatabaseBackend,
) -> dict[str, Any]:
    """Per-query validation: SQL EXPLAIN, params well-formed, max_rows_default > 0."""
    # ... body moved verbatim ...
```

### `verification/__init__.py` (extended)

```python
from mcp_tools_sql.verification.queries import verify_queries

__all__ = [
    ...,
    "verify_queries",
]
# verify_one_query is intentionally NOT re-exported — submodule-internal.
```

### `tests/verification/test_queries.py`

Move tests from `tests/cli/test_verify.py` (lines ~650–805 + ~1267–1287),
updating imports:

```python
from mcp_tools_sql.backends.mssql import MSSQLBackend
from mcp_tools_sql.verification import verify_queries
from mcp_tools_sql.verification.queries import verify_one_query
```

(The per-entry equality test imports `verify_one_query` from the submodule
directly because it's not re-exported.)

**Imports to add (do not forget):**
- `from mcp_tools_sql.backends.mssql import MSSQLBackend` — used by the
  test `test_verify_queries_unimplemented_backend_explain_fails_cleanly`
  (and any other test that instantiates `MSSQLBackend` to exercise the
  unimplemented-backend path). Verified path:
  `src/mcp_tools_sql/backends/mssql.py` exposes the `MSSQLBackend` class.

Tests use the new `sqlite_backend` fixture from
`tests/verification/conftest.py` instead of the local
`_open_sqlite_backend` helper.

Tests moved:
- `test_verify_queries_valid_sqlite`
- `test_verify_queries_detects_invalid_sql`
- `test_verify_queries_detects_param_mismatch`
- `test_verify_queries_detects_invalid_param_type`
- `test_verify_queries_rejects_filter_and_max_rows_as_non_sql_params`
- `test_verify_queries_detects_missing_max_rows_default`
- `test_verify_queries_unimplemented_backend_explain_fails_cleanly`
- `test_verify_one_query_matches_bulk_happy_path`

## HOW

### Recommended tool

```
move_symbol(
    source_file="src/mcp_tools_sql/cli/commands/verify.py",
    symbol_names=[
        "_VALID_PARAM_TYPES",
        "_DUMMY_BY_TYPE",
        "_check_sql_explain",
        "_check_params_well_formed",
        "verify_one_query",
        "verify_queries",
    ],
    dest_file="src/mcp_tools_sql/verification/queries.py",
)
```

Then manually:
1. Add the imports at the top.
2. Re-export `verify_queries` from `verification/__init__.py`.
3. Move the tests; rewrite the `try / backend.close()` pattern to use the
   new `sqlite_backend` fixture (or keep the explicit pattern if the
   `move_symbol` move keeps tests verbatim — simpler).

### Integration in `cli/commands/verify.py`

Add to the top-level import block:

```python
from mcp_tools_sql.verification import verify_queries
```

`run()` continues to call `verify_queries(query_config.queries,
connection.backend, open_backend)` unchanged.

## ALGORITHM

No algorithm — functions moved verbatim.

## DATA

- `verify_one_query` returns a 3-entry dict: `<name>.sql`, `<name>.params`,
  `<name>.max_rows_default`. **Insertion order is load-bearing.**
- `verify_queries` returns one such block per query, plus `overall_ok`.

## Checks

Run after edits:
- `mcp__mcp-tools-py__run_pylint_check`
- `mcp__mcp-tools-py__run_mypy_check`
- `mcp__mcp-tools-py__run_pytest_check(extra_args=["-n", "auto", "-m", "not git_integration and not claude_cli_integration and not claude_api_integration and not formatter_integration and not github_integration and not langchain_integration"])`
- `mcp__mcp-tools-py__run_tach_check`
- `mcp__mcp-tools-py__run_lint_imports_check`

All must pass. **Explicitly run the snapshot test** to confirm dict order
preservation:

```
mcp__mcp-tools-py__run_pytest_check(extra_args=[
    "tests/cli/test_verify.py::test_verify_cli_queries_updates_snapshot", "-v"
])
```

## LLM Prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_7.md`. Implement
> step 7: move `_VALID_PARAM_TYPES`, `_DUMMY_BY_TYPE`, `_check_sql_explain`,
> `_check_params_well_formed`, `verify_one_query`, and `verify_queries`
> from `cli/commands/verify.py` to a new file
> `src/mcp_tools_sql/verification/queries.py`. Use the `move_symbol` MCP
> tool to relocate all six symbols in one call — this preserves dict
> insertion order exactly. **Re-export only `verify_queries` from
> `verification/__init__.py`** (verify_one_query stays submodule-internal
> per the issue). Move the eight queries-related tests from
> `tests/cli/test_verify.py` to `tests/verification/test_queries.py`. The
> per-entry equality test imports `verify_one_query` from
> `mcp_tools_sql.verification.queries` directly. Do not refactor any
> function body. After running standard checks, explicitly run the CLI
> snapshot test (`test_verify_cli_queries_updates_snapshot`) to confirm
> byte-equal output. All must pass before committing.
