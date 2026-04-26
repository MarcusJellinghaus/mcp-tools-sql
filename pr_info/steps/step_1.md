# Step 1: Config Model Changes + Backend ABC Simplification

## Context
See [summary.md](./summary.md) for full issue context. This step extends the config model with per-backend SQL support and removes introspection methods from the backend ABC.

## LLM Prompt
> Implement step 1 of issue #4 (see `pr_info/steps/summary.md` and `pr_info/steps/step_1.md`).
> Add `BackendQueryConfig` model and `resolve_sql()` to `QueryConfig`. Remove introspection methods from the backend ABC and all backend implementations. Update all affected tests. TDD: write tests first, then implementation.

## Part A: Config model changes

### WHERE
- `tests/config/test_models.py` (tests first)
- `src/mcp_tools_sql/config/models.py`

### WHAT — New model
```python
class BackendQueryConfig(BaseModel):
    """Per-backend SQL override for a query."""
    sql: str
```

### WHAT — Extended `QueryConfig`
```python
class QueryConfig(BaseModel):
    description: str = ""
    sql: str
    params: dict[str, QueryParamConfig] = {}
    max_rows: int = 100
    backends: dict[str, BackendQueryConfig] = {}

    def resolve_sql(self, backend_name: str) -> str:
        """Return backend-specific SQL if override exists, else default sql."""
```

### ALGORITHM — `resolve_sql`
```
if backend_name in self.backends:
    return self.backends[backend_name].sql
return self.sql
```

### DATA — Test cases for `resolve_sql`
```python
# Override present → returns backend SQL
config = QueryConfig(sql="DEFAULT", backends={"sqlite": BackendQueryConfig(sql="SQLITE")})
assert config.resolve_sql("sqlite") == "SQLITE"

# Override absent → returns default SQL
assert config.resolve_sql("mssql") == "DEFAULT"

# No backends at all → returns default SQL
config2 = QueryConfig(sql="DEFAULT")
assert config2.resolve_sql("sqlite") == "DEFAULT"
```

### WHAT — Tests to add (`tests/config/test_models.py`)
```python
class TestBackendQueryConfig:
    def test_basic_creation(self) -> None: ...

class TestQueryConfigResolveSQL:
    def test_override_present(self) -> None: ...
    def test_override_absent_fallback(self) -> None: ...
    def test_no_backends_fallback(self) -> None: ...

class TestQueryConfigBackendsParsing:
    def test_nested_dict_parsing(self) -> None: ...  # simulate TOML structure
```

## Part B: Backend ABC simplification

### WHERE
- `src/mcp_tools_sql/backends/base.py` — remove 4 abstract methods
- `src/mcp_tools_sql/backends/sqlite.py` — remove 4 method implementations + `fnmatch` import
- `src/mcp_tools_sql/backends/mssql.py` — remove 4 method stubs
- `tests/backends/test_sqlite.py` — remove `TestSchemaIntrospection` class, update `_DATA_METHODS`

### WHAT — Methods to remove from ABC
```python
# DELETE these from DatabaseBackend:
read_schemas(self) -> list[str]
read_tables(self, schema: str) -> list[str]
read_columns(self, schema: str, table: str, filter_pattern: str | None = None) -> list[dict[str, Any]]
read_relations(self, schema: str, table: str) -> list[dict[str, Any]]
```

### WHAT — Test updates (`tests/backends/test_sqlite.py`)
- Remove entire `TestSchemaIntrospection` class (7 tests) — these will be replaced by tool-level integration tests in step 5
- Update `_DATA_METHODS` list: remove `read_schemas`, `read_tables`, `read_columns`, `read_relations` entries
- Update `TestConnection.test_connect_and_close`: replace `backend.read_tables("main")` with `backend.execute_query("SELECT name FROM sqlite_master WHERE type='table'")`
- Update `TestConnection.test_connect_idempotent`: same replacement
- Update `TestConnection.test_context_manager`: same replacement
- Remove `test_read_columns_nonexistent_table` and `test_read_tables_nonexistent_schema` from `TestErrorHandling`

### HOW — Verify
- All remaining backend tests pass
- Config model tests pass
- mypy passes (no references to removed methods)
- pylint passes
