# Step 2: SQLite Backend Implementation

> **Context**: See [summary.md](./summary.md) for full implementation overview.

## Goal

Implement all `DatabaseBackend` methods in `SQLiteBackend`. This is the first concrete backend — it uses only the `sqlite3` stdlib module.

## WHERE

| File | Action |
|------|--------|
| `src/mcp_tools_sql/backends/sqlite.py` | Modify |

## WHAT

### Connection management

```python
def __init__(self, config: ConnectionConfig) -> None:
    self._config = config
    self._connection: sqlite3.Connection | None = None

def connect(self) -> None:
    # Idempotent — no-op if already connected
    # Raise ValueError on empty path
    # sqlite3.connect(path, check_same_thread=False)
    # Set row_factory = sqlite3.Row

def close(self) -> None:
    # Safe to call multiple times
    # Close connection, set _connection = None
```

### Query execution

```python
def execute_query(self, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    # Execute SELECT with named :param style
    # Convert sqlite3.Row results to list[dict]

def execute_update(self, sql: str, params: dict[str, Any] | None = None) -> int:
    # Execute statement, commit, return cursor.rowcount

def explain(self, sql: str) -> str:
    # Run "EXPLAIN QUERY PLAN " + sql
    # Return detail column values joined with newlines
```

### Schema introspection

```python
def read_schemas(self) -> list[str]:
    # Return ["main"]

def read_tables(self, schema: str) -> list[str]:
    # SELECT name FROM sqlite_master WHERE type='table'
    # Exclude sqlite_ internal tables

def read_columns(self, schema: str, table: str, filter_pattern: str | None = None) -> list[dict[str, Any]]:
    # PRAGMA table_info(table)
    # Normalize keys: name, type, nullable (inverted notnull), default (dflt_value), is_primary_key (pk > 0)
    # Apply LIKE-style filter_pattern in Python (fnmatch) if provided

def read_relations(self, schema: str, table: str) -> list[dict[str, Any]]:
    # PRAGMA foreign_key_list(table)
    # Normalize: constraint_name=fk_{id}, column=from, referenced_table=table, referenced_column=to, on_update, on_delete
```

## HOW

- `import sqlite3` (stdlib)
- `from fnmatch import fnmatch` for LIKE-style pattern matching on column names
- Use `sqlite3.Row` as row factory for dict conversion
- Named parameters use `:name` style (sqlite3 native)
- All methods that need the connection should raise a clear error if `_connection is None` (not connected)

## ALGORITHM

### `connect()`
```
if already connected: return (idempotent)
if path is empty string: raise ValueError
conn = sqlite3.connect(path, check_same_thread=False)
conn.row_factory = sqlite3.Row
self._connection = conn
```

### `read_columns()` normalization
```
rows = execute PRAGMA table_info(table)
for each row:
    normalize to {name, type, nullable=not notnull, default=dflt_value, is_primary_key=pk>0}
if filter_pattern:
    keep only rows where fnmatch(name, filter_pattern)  # case-insensitive
return normalized rows
```

### `read_relations()` normalization
```
rows = execute PRAGMA foreign_key_list(table)
for each row:
    normalize to {constraint_name=fk_{id}, column=from, referenced_table=table, referenced_column=to, on_update, on_delete}
return normalized rows
```

## DATA

### Column metadata (normalized)
```python
{"name": "id", "type": "INTEGER", "nullable": False, "default": None, "is_primary_key": True}
```

### Relation metadata (normalized)
```python
{"constraint_name": "fk_0", "column": "customer_id", "referenced_table": "customers", "referenced_column": "id", "on_update": "NO ACTION", "on_delete": "NO ACTION"}
```

## LLM Prompt

```
Implement Step 2 from pr_info/steps/step_2.md (see pr_info/steps/summary.md for context).

Implement all DatabaseBackend methods in SQLiteBackend (src/mcp_tools_sql/backends/sqlite.py):
- connect/close with idempotent behavior, ValueError on empty path, check_same_thread=False
- execute_query/execute_update with named :param parameters
- explain via EXPLAIN QUERY PLAN
- read_schemas returns ["main"]
- read_tables queries sqlite_master
- read_columns uses PRAGMA table_info with normalized keys (name, type, nullable, default, is_primary_key) and optional fnmatch filter
- read_relations uses PRAGMA foreign_key_list with normalized keys (constraint_name as fk_{id}, column, referenced_table, referenced_column, on_update, on_delete)

Use sqlite3.Row for dict conversion. Raise clear errors when not connected.

Run all quality checks (pylint, mypy, pytest) and fix any issues.
```
