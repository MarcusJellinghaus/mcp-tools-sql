# Step 1: ABC Updates + Stub Cleanup

> **Context**: See [summary.md](./summary.md) for full implementation overview.

## Goal

Refine the `DatabaseBackend` ABC: remove the redundant `search_columns` method and add context manager support. Update both backend stubs to match.

## WHERE

| File | Action |
|------|--------|
| `src/mcp_tools_sql/backends/base.py` | Modify |
| `src/mcp_tools_sql/backends/sqlite.py` | Modify |
| `src/mcp_tools_sql/backends/mssql.py` | Modify |
| `vulture_whitelist.py` | Modify — Remove `_.search_columns` entry |

## WHAT

### `base.py` — Remove + Add

**Remove** the `search_columns` abstract method entirely.

**Add** context manager methods to `DatabaseBackend`:

```python
def __enter__(self) -> Self:
    """Connect and return self for use as context manager."""
    self.connect()
    return self

def __exit__(
    self,
    exc_type: type[BaseException] | None,
    exc_val: BaseException | None,
    exc_tb: TracebackType | None,
) -> None:
    """Close connection on context exit."""
    self.close()
```

- These are **concrete** methods (not abstract) — all backends inherit them.
- Import `Self` from `typing` (Python 3.11+) and `TracebackType` from `types`.

### `sqlite.py` — Remove `search_columns` stub method

### `mssql.py` — Remove `search_columns` stub method

### `vulture_whitelist.py` — Remove `_.search_columns` entry

Remove the `_.search_columns` line from the vulture whitelist since the method no longer exists.

## HOW

- `from typing import Self` (available in 3.11+, which is the project minimum)
- `from types import TracebackType`
- No new dependencies, no config changes

## DATA

No new data structures. The context manager returns `Self` (the backend subclass instance).

## Tests

No dedicated tests in this step — context manager tests are covered in Step 3 with the full SQLite implementation. The existing smoke tests (`test_create_backend_sqlite`, `test_create_backend_unknown`) verify the stubs still work after removal.

## LLM Prompt

```
Implement Step 1 from pr_info/steps/step_1.md (see pr_info/steps/summary.md for context).

Update the DatabaseBackend ABC in backends/base.py:
1. Remove the `search_columns` abstract method
2. Add `__enter__`/`__exit__` context manager with default implementation (calls connect/close)
3. `__enter__` returns `Self`, `__exit__` accepts standard exception args

Remove `search_columns` from both backend stubs (sqlite.py and mssql.py).
Remove `_.search_columns` from `vulture_whitelist.py`.

Run all quality checks (pylint, mypy, pytest) and fix any issues.
```
