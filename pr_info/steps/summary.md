# Summary: Backend Abstraction + SQLite Implementation (#3)

## Overview

Implement the SQLite database backend and refine the `DatabaseBackend` ABC. SQLite is the first real backend — it uses no external dependencies and becomes the foundation for all CI testing.

## Architectural / Design Changes

### ABC refinement (`DatabaseBackend`)
- **Remove `search_columns`** — redundant with `read_columns(filter_pattern=...)`. One method, one responsibility.
- **Add context manager protocol** — `__enter__`/`__exit__` with default implementation in base class (calls `connect()`/`close()`). All backends inherit this for free. `__enter__` returns `Self` for correct subclass typing.

### SQLite backend (first concrete implementation)
- All methods implemented against `sqlite3` stdlib module — zero external dependencies.
- **Normalized metadata**: Column and relation introspection returns consistent keys across backends (`name`, `type`, `nullable`, `default`, `is_primary_key` for columns; `constraint_name`, `column`, `referenced_table`, `referenced_column`, `on_update`, `on_delete` for relations).
- **Thread safety**: `check_same_thread=False` for FastMCP async compatibility.
- **Truncation boundary**: Backend returns all data; truncation for LLM context windows is handled at the tool layer (out of scope).

### Design decisions
| Decision | Rationale |
|----------|-----------|
| `search_columns` removed from ABC + all stubs | Redundant with `filter_pattern` param on `read_columns` |
| Context manager in base class | Inherited by all backends, zero per-backend work |
| `__enter__` returns `Self` | Correct subclass typing in `with` blocks |
| Normalized column/relation keys | Consistent output regardless of backend |
| `check_same_thread=False` | FastMCP dispatches across threads |
| Empty path raises `ValueError` | Prevents silent in-memory fallback |
| Backend returns all columns | Truncation is a presentation concern (tool layer) |

## Files Modified

| File | Action | Purpose |
|------|--------|---------|
| `src/mcp_tools_sql/backends/base.py` | Modify | Remove `search_columns`, add `__enter__`/`__exit__` |
| `src/mcp_tools_sql/backends/sqlite.py` | Modify | Implement all backend methods |
| `src/mcp_tools_sql/backends/mssql.py` | Modify | Remove `search_columns` stub |
| `tests/backends/__init__.py` | Create | Test package init |
| `tests/backends/test_sqlite.py` | Create | Comprehensive SQLite tests |

## Implementation Steps

1. **ABC updates + stub cleanup** — Remove `search_columns` from ABC, SQLite, and MSSQL stubs. Add context manager to ABC.
2. **SQLite backend implementation** — Implement all `DatabaseBackend` methods with normalized metadata output.
3. **SQLite tests** — Comprehensive tests for introspection, queries, context manager, and error handling.
