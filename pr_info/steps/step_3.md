# Step 3: SQLite Backend Tests

> **Context**: See [summary.md](./summary.md) for full implementation overview.

## Goal

Write comprehensive tests for the SQLite backend covering introspection, query execution, context manager, and error handling.

## WHERE

| File | Action |
|------|--------|
| `tests/backends/__init__.py` | Create (empty) |
| `tests/backends/test_sqlite.py` | Create |

## WHAT

All tests use the `sqlite_integration` marker. Use the existing `sqlite_db` fixture from `tests/conftest.py` (creates a file-based DB with `customers` and `orders` tables + seed data).

### Test categories

**Connection & context manager:**
- `test_connect_and_close` — connect, verify operational, close, verify closed
- `test_connect_idempotent` — calling connect twice is a no-op
- `test_close_idempotent` — calling close twice doesn't raise
- `test_context_manager` — `with` block connects/closes automatically
- `test_context_manager_returns_backend` — `as` variable is the backend instance

**Schema introspection:**
- `test_read_schemas` — returns `["main"]`
- `test_read_tables` — returns `customers` and `orders`, excludes sqlite internals
- `test_read_columns` — normalized keys for customers table
- `test_read_columns_with_filter` — filter_pattern narrows results
- `test_read_columns_filter_no_match` — returns empty list
- `test_read_relations` — normalized FK from orders → customers
- `test_read_relations_no_fks` — customers table returns empty list

**Query execution:**
- `test_execute_query` — SELECT with params returns list[dict]
- `test_execute_query_no_params` — SELECT without params
- `test_execute_update` — INSERT returns rowcount=1
- `test_explain` — returns non-empty string with plan details

**Error handling:**
- `test_connect_empty_path` — raises `ValueError`
- `test_operations_before_connect` — raises error for each data-access method (`execute_query`, `execute_update`, `explain`, `read_schemas`, `read_tables`, `read_columns`, `read_relations`). Use `@pytest.mark.parametrize`.
- `test_operations_after_close` — raises error for each data-access method. Use `@pytest.mark.parametrize`.
- `test_read_columns_nonexistent_table` — raises error
- `test_read_tables_nonexistent_schema` — behavior is defined (SQLite ignores schema)
- `test_connect_invalid_path` — path in non-existent directory
- `test_connect_readonly_file` — permission error on write operations
- `test_connect_corrupt_db` — corrupt file raises error

## HOW

- Helper function to create `SQLiteBackend` from a path:
  ```python
  def _make_backend(path: str) -> SQLiteBackend:
      return SQLiteBackend(ConnectionConfig(backend="sqlite", path=path))
  ```
- Use `tmp_path` fixture for file-based tests
- Use existing `sqlite_db` fixture for seeded database tests
- Mark all tests with `@pytest.mark.sqlite_integration`

## DATA

Tests verify the normalized metadata structures defined in Step 2:
- Column dict: `{"name", "type", "nullable", "default", "is_primary_key"}`
- Relation dict: `{"constraint_name", "column", "referenced_table", "referenced_column", "on_update", "on_delete"}`

## LLM Prompt

```
Implement Step 3 from pr_info/steps/step_3.md (see pr_info/steps/summary.md for context).

Create tests/backends/__init__.py (empty) and tests/backends/test_sqlite.py.

Write comprehensive tests for SQLiteBackend covering:
1. Connection lifecycle: connect, close, idempotent behavior, context manager
2. Schema introspection: read_schemas, read_tables, read_columns (with/without filter), read_relations (normalized keys)
3. Query execution: execute_query with/without params, execute_update, explain
4. Error handling: empty path (ValueError), operations before connect (parametrized over all 7 data methods), operations after close (parametrized), nonexistent table, invalid path, read-only file, corrupt DB

Use existing sqlite_db fixture from conftest.py. Mark all tests with @pytest.mark.sqlite_integration.
Helper: _make_backend(path) creates SQLiteBackend from ConnectionConfig.

Run all quality checks (pylint, mypy, pytest) and fix any issues.
```
