# Step 5: Integration Tests

## Context
See [summary.md](./summary.md) for full issue context. This step adds end-to-end tests that verify the full pipeline: TOML config → tool registration → MCP protocol → SQLite execution → formatted output.

## LLM Prompt
> Implement step 5 of issue #4 (see `pr_info/steps/summary.md` and `pr_info/steps/step_5.md`).
> Add integration tests for all 4 schema tools via MCP protocol. Test against real SQLite databases. Cover truncation, filter, param stripping, and edge cases. Use the in-memory MCP client pattern from `tests/test_dynamic_tool_registration.py`.

### WHERE
- `tests/test_schema_tools.py` (extend file from step 4)
- `tests/conftest.py` (add wide-table fixture)

### WHAT — New fixture (`tests/conftest.py`)
```python
@pytest.fixture
def sqlite_wide_db(tmp_path: Path) -> Generator[Path, None, None]:
    """Create a SQLite database with a wide table (150 columns) for truncation tests."""
```

### ALGORITHM — Wide table fixture
```
columns = ", ".join(f"col_{i} TEXT" for i in range(150))
create_sql = f"CREATE TABLE wide_table ({columns})"
# Insert 1 row so table exists with data
conn.execute(create_sql)
conn.execute(insert with placeholder values)
```

### WHAT — Helper to create MCP with registered tools
```python
def _make_mcp_with_tools(db_path: str) -> FastMCP:
    """Create a FastMCP instance with builtin tools registered against a SQLite DB."""
    config = ConnectionConfig(backend="sqlite", connection_string=db_path)
    backend = SQLiteBackend(config)
    backend.connect()
    mcp = FastMCP("test-schema-tools")
    register_builtin_tools(mcp, backend, "sqlite")
    return mcp
```

### WHAT — MCP protocol integration tests
```python
@pytest.mark.asyncio
class TestSchemaToolsMcpProtocol:
    async def test_all_four_tools_discoverable(self, sqlite_db: Path) -> None:
        """list_tools() returns read_schemas, read_tables, read_columns, read_relations."""

    async def test_read_schemas(self, sqlite_db: Path) -> None:
        """call_tool('read_schemas') returns formatted table with 'main'."""

    async def test_read_tables(self, sqlite_db: Path) -> None:
        """call_tool('read_tables', {schema: 'main'}) returns customers and orders."""

    async def test_read_columns(self, sqlite_db: Path) -> None:
        """call_tool('read_columns', {schema: 'main', table: 'customers'}) returns column metadata."""

    async def test_read_columns_with_filter(self, sqlite_db: Path) -> None:
        """call_tool('read_columns', {schema: 'main', table: 'customers', filter: 'na*'}) filters by glob."""

    async def test_read_columns_filter_no_match(self, sqlite_db: Path) -> None:
        """Filter with no matches returns 'No results found.'"""

    async def test_read_relations(self, sqlite_db: Path) -> None:
        """call_tool('read_relations', {schema: 'main', table: 'orders'}) returns FK info."""

    async def test_read_relations_no_fks(self, sqlite_db: Path) -> None:
        """Table without FKs returns 'No results found.'"""
```

### WHAT — Truncation tests
```python
@pytest.mark.asyncio
class TestSchemaToolsTruncation:
    async def test_wide_table_truncation(self, sqlite_wide_db: Path) -> None:
        """read_columns on 150-column table with default max_rows=100 shows truncation message."""

    async def test_wide_table_custom_max_rows(self, sqlite_wide_db: Path) -> None:
        """read_columns with max_rows=10 truncates at 10 and shows message."""

    async def test_no_truncation_within_limit(self, sqlite_db: Path) -> None:
        """Small table with 3 columns → no truncation message."""
```

### WHAT — Param stripping tests
```python
@pytest.mark.asyncio
class TestParamStripping:
    async def test_schema_param_ignored_for_sqlite(self, sqlite_db: Path) -> None:
        """read_tables accepts schema param but SQLite SQL doesn't use it — no error."""

    async def test_read_schemas_no_params(self, sqlite_db: Path) -> None:
        """read_schemas has no params in SQLite SQL — works with empty args."""
```

### WHAT — Edge case tests
```python
@pytest.mark.asyncio
class TestSchemaToolsEdgeCases:
    async def test_empty_database(self, tmp_path: Path) -> None:
        """read_tables on empty database returns 'No results found.'"""

    async def test_read_columns_nonexistent_table(self, sqlite_db: Path) -> None:
        """read_columns on non-existent table returns 'No results found.'"""

    async def test_tool_schemas_have_descriptions(self, sqlite_db: Path) -> None:
        """All tools have non-empty descriptions from TOML config."""
```

### HOW — MCP client pattern
Use `mcp.shared.memory.create_connected_server_and_client_session` as in existing tests:
```python
async with create_connected_server_and_client_session(mcp, raise_exceptions=True) as client:
    result = await client.call_tool("read_schemas", {})
    text = result.content[0].text
    assert "main" in text
```

### HOW — Verify
- All integration tests pass
- All existing tests still pass
- mypy, pylint pass
- Full pipeline works: TOML → config → dynamic function → MCP protocol → SQLite → tabulate → text
