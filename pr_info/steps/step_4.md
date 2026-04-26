# Step 4: Tool Registration Pipeline + Server Wiring

## Context
See [summary.md](./summary.md) for full issue context. This is the core step: build the config-driven tool registration pipeline and wire it into the MCP server. Reuses the dynamic function builder pattern proven in the spike (`tests/test_dynamic_tool_registration.py`).

## LLM Prompt
> Implement step 4 of issue #4 (see `pr_info/steps/summary.md` and `pr_info/steps/step_4.md`).
> Rewrite `schema_tools.py` with plain functions for config-driven tool registration. Wire into `server.py`. The dynamic function builder pattern is proven in `tests/test_dynamic_tool_registration.py` — adapt it for real query execution. TDD: write unit tests for param stripping and filter logic, then implement.

## Part A: `schema_tools.py` — Tool registration functions

### WHERE
- `src/mcp_tools_sql/schema_tools.py` (rewrite, replace class with functions)

### WHAT — Public function
```python
def register_builtin_tools(
    mcp: FastMCP,
    backend: DatabaseBackend,
    backend_name: str,
) -> None:
    """Load default_queries.toml and register all 4 schema tools on mcp."""
```

### WHAT — Private helpers
```python
def _build_tool_fn(
    name: str,
    config: QueryConfig,
    backend: DatabaseBackend,
    backend_name: str,
) -> Callable[..., Any]:
    """Build a dynamic async function for one query config entry.

    Returns an async function with __signature__ set from config params,
    ready for mcp.add_tool().
    """

def _extract_sql_params(sql: str) -> set[str]:
    """Scan SQL for :param_name references, return set of param names."""

def _apply_filter(
    rows: list[dict[str, Any]],
    filter_pattern: str | None,
) -> list[dict[str, Any]]:
    """Apply fnmatch glob filter on the 'name' column. Returns filtered rows."""
```

### ALGORITHM — `register_builtin_tools`
```
queries = load_default_queries()
for name, config in queries.items():
    fn = _build_tool_fn(name, config, backend, backend_name)
    mcp.add_tool(fn)
```

### ALGORITHM — `_build_tool_fn`
```
resolved_sql = config.resolve_sql(backend_name)
sql_params = _extract_sql_params(resolved_sql)
# Build signature from config.params (union of all params across backends)
# Create async function that:
#   1. Receives **kwargs from MCP call
#   2. Extracts max_rows from kwargs (default from config.max_rows)
#      For the `max_rows` parameter, use `config.max_rows` as the default
#      value in the generated function signature. `QueryConfig.max_rows`
#      provides the default; `params.max_rows` makes it a user-overridable
#      tool parameter.
#   3. Extracts filter from kwargs (if present)
#   4. Strips kwargs to only params referenced in resolved SQL
#   5. Calls backend.execute_query(resolved_sql, stripped_params)
#   6. Applies _apply_filter if filter_pattern provided
#   7. Returns format_rows(rows, max_rows)
# Set __signature__, __name__, __doc__ on the function
# Return it
```

### ALGORITHM — `_extract_sql_params`
```
import re
return set(re.findall(r":(\w+)", sql))
```

### ALGORITHM — `_apply_filter`
```
if not filter_pattern:
    return rows
return [r for r in rows if fnmatch(str(r.get("name", "")).lower(), filter_pattern.lower())]
```

### DATA — Dynamic function signature construction
Reuse the pattern from `tests/test_dynamic_tool_registration.py:_make_dynamic_tool_fn`:
- Iterate `config.params`, build `inspect.Parameter` with `Annotated[type, Field(description=...)]`
- Required params get `default=inspect.Parameter.empty`
- Optional params get `default=None` and `Optional[type]` annotation
- Set `__signature__`, `__name__`, `__doc__` on the function

### HOW — Special params (`filter`, `max_rows`)
- `filter` and `max_rows` are tool parameters defined in TOML params, not SQL params
- They are consumed in Python (filter → fnmatch, max_rows → truncation) and stripped before SQL execution
- `_extract_sql_params` naturally excludes them since they don't appear as `:filter` or `:max_rows` in the SQL

## Part B: `server.py` — FastMCP wiring

### WHERE
- `src/mcp_tools_sql/server.py`

### WHAT — Changes to `ToolServer`
```python
class ToolServer:
    def __init__(self, config: QueryFileConfig, backend: DatabaseBackend) -> None:
        self._config = config
        self._backend = backend
        self._mcp = FastMCP("mcp-tools-sql")

    @property
    def mcp(self) -> FastMCP:
        """Expose FastMCP instance (for testing)."""
        return self._mcp

    def _register_builtin_tools(self) -> None:
        """Register schema-exploration tools from default_queries.toml."""
        backend_name = self._config.connection  # or derive from backend type
        register_builtin_tools(self._mcp, self._backend, backend_name)

    def _register_configured_tools(self) -> None:
        # TODO: issue #5
        pass  # no longer raises NotImplementedError

    def run(self) -> None:
        self._register_builtin_tools()
        self._register_configured_tools()
        self._mcp.run(transport="stdio")
```

### HOW — Backend name resolution
The `backend_name` needed for `resolve_sql()` should match the keys in `default_queries.toml` (e.g., `"sqlite"`, `"mssql"`). Derive from `backend.__class__` or the connection config's `backend` field. Simplest: pass `ConnectionConfig.backend` through to the server. The `ToolServer` receives `QueryFileConfig` which has `connection` (a name reference). The resolved `ConnectionConfig.backend` field has the value we need.

Update `ToolServer.__init__` to also accept `backend_name: str`:
```python
def __init__(self, config: QueryFileConfig, backend: DatabaseBackend, backend_name: str) -> None:
```

Update `create_server()` accordingly. Note: `create_server()` passes `ConnectionConfig.backend` as `backend_name` — no default needed.

## Part C: Unit tests for helpers

### WHERE
- `tests/test_schema_tools.py` (new file)

### WHAT — Tests
```python
class TestExtractSqlParams:
    def test_single_param(self) -> None:
        assert _extract_sql_params("SELECT * WHERE x = :id") == {"id"}

    def test_multiple_params(self) -> None:
        assert _extract_sql_params("WHERE a = :x AND b = :y") == {"x", "y"}

    def test_no_params(self) -> None:
        assert _extract_sql_params("SELECT 'main' AS name") == set()

    def test_duplicate_param(self) -> None:
        assert _extract_sql_params("WHERE a = :x OR b = :x") == {"x"}

class TestApplyFilter:
    def test_no_filter(self) -> None:
        """None filter returns all rows."""

    def test_glob_match(self) -> None:
        """Glob pattern filters rows by 'name' field."""

    def test_case_insensitive(self) -> None:
        """Filter is case-insensitive."""

    def test_no_match(self) -> None:
        """No matching rows returns empty list."""
```

### HOW — Verify
- All unit tests pass
- All existing tests still pass
- mypy, pylint pass
- `_register_configured_tools` changed from `raise NotImplementedError` to `pass`
