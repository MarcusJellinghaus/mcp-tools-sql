# Step 2: `default_queries.toml` + Package Data

## Context
See [summary.md](./summary.md) for full issue context. This step creates the TOML file defining the 4 built-in schema introspection queries with per-backend SQL overrides, and configures packaging.

## LLM Prompt
> Implement step 2 of issue #4 (see `pr_info/steps/summary.md` and `pr_info/steps/step_2.md`).
> Create `default_queries.toml` with the 4 schema queries and SQLite overrides. Add a loader helper. Update package-data config. TDD: write a test that loads and validates the TOML, then create the file.

## Part A: TOML file creation

### WHERE
- `src/mcp_tools_sql/default_queries.toml` (new file)

### WHAT — 4 query definitions

**`read_schemas`** — list schema names
```toml
[queries.read_schemas]
description = "List database schema names"
sql = "SELECT SCHEMA_NAME AS name FROM INFORMATION_SCHEMA.SCHEMATA ORDER BY name"

[queries.read_schemas.backends.sqlite]
sql = "SELECT 'main' AS name"
```

**`read_tables`** — list tables in a schema
```toml
[queries.read_tables]
description = "List tables in a schema"
sql = "SELECT TABLE_NAME AS name FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = :schema ORDER BY name"

[queries.read_tables.params.schema]
name = "schema"
type = "str"
description = "Schema name"

[queries.read_tables.backends.sqlite]
sql = "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
```

**`read_columns`** — column metadata
```toml
[queries.read_columns]
description = "List column metadata for a table"
sql = "SELECT COLUMN_NAME AS name, DATA_TYPE AS type, IS_NULLABLE AS nullable, COLUMN_DEFAULT AS \"default\", CASE WHEN COLUMN_KEY = 'PRI' THEN 1 ELSE 0 END AS is_primary_key FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = :schema AND TABLE_NAME = :table ORDER BY ORDINAL_POSITION"
max_rows = 100

[queries.read_columns.params.schema]
name = "schema"
type = "str"
description = "Schema name"

[queries.read_columns.params.table]
name = "table"
type = "str"
description = "Table name"

[queries.read_columns.params.filter]
name = "filter"
type = "str"
description = "Glob pattern to filter column names (e.g. 'user_*')"
required = false

[queries.read_columns.params.max_rows]
name = "max_rows"
type = "int"
description = "Maximum rows to return (default 100)"
required = false

[queries.read_columns.backends.sqlite]
sql = "SELECT name, type, NOT \"notnull\" AS nullable, dflt_value AS \"default\", pk > 0 AS is_primary_key FROM pragma_table_info(:table)"
```

**`read_relations`** — FK relationships
```toml
[queries.read_relations]
description = "List foreign key relationships for a table"
sql = """\
SELECT
    rc.CONSTRAINT_NAME AS constraint_name,
    kcu1.COLUMN_NAME AS "column",
    kcu2.TABLE_NAME AS referenced_table,
    kcu2.COLUMN_NAME AS referenced_column
FROM INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS rc
JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu1
    ON kcu1.CONSTRAINT_NAME = rc.CONSTRAINT_NAME
    AND kcu1.TABLE_SCHEMA = rc.CONSTRAINT_SCHEMA
JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu2
    ON kcu2.CONSTRAINT_NAME = rc.UNIQUE_CONSTRAINT_NAME
    AND kcu2.TABLE_SCHEMA = rc.UNIQUE_CONSTRAINT_SCHEMA
    AND kcu2.ORDINAL_POSITION = kcu1.ORDINAL_POSITION
WHERE kcu1.TABLE_SCHEMA = :schema AND kcu1.TABLE_NAME = :table
"""

[queries.read_relations.params.schema]
name = "schema"
type = "str"
description = "Schema name"

[queries.read_relations.params.table]
name = "table"
type = "str"
description = "Table name"

[queries.read_relations.backends.sqlite]
sql = "SELECT id AS constraint_name, \"from\" AS \"column\", \"table\" AS referenced_table, \"to\" AS referenced_column FROM pragma_foreign_key_list(:table)"
```

### DATA — Note on SQLite pragma function-form
The issue flags `pragma_table_info(:table)` as needing verification. SQLite supports function-form PRAGMAs with named params when using `sqlite3.Row` row factory. This must be verified in the test (Part B). If it fails, fallback: use `SELECT ... FROM pragma_table_info(:table)` (table-valued function syntax) since `execute_query` uses dict params. Same approach for `pragma_foreign_key_list(:table)`.

## Part B: Loader helper + test

### WHERE
- `tests/test_default_queries.py` (new file, tests first)
- `src/mcp_tools_sql/schema_tools.py` (loader helper)

### WHAT — Loader function
```python
def load_default_queries() -> dict[str, QueryConfig]:
    """Load built-in schema queries from default_queries.toml.

    Returns:
        Dict mapping query name to QueryConfig.
    """
```

### ALGORITHM
```
toml_path = Path(__file__).parent / "default_queries.toml"
data = tomllib.load(toml_path)
return {name: QueryConfig.model_validate(cfg) for name, cfg in data["queries"].items()}
```

### WHAT — Tests (`tests/test_default_queries.py`)
```python
class TestDefaultQueriesLoading:
    def test_loads_four_queries(self) -> None:
        """load_default_queries() returns exactly 4 entries."""

    def test_query_names(self) -> None:
        """Expected keys: read_schemas, read_tables, read_columns, read_relations."""

    def test_sqlite_overrides_present(self) -> None:
        """Each query has a backends.sqlite entry."""

    def test_resolve_sql_sqlite(self) -> None:
        """resolve_sql('sqlite') returns SQLite-specific SQL for each query."""

    def test_read_columns_has_filter_param(self) -> None:
        """read_columns has an optional 'filter' param."""

    def test_read_columns_has_max_rows_param(self) -> None:
        """read_columns has an optional 'max_rows' param and config.max_rows == 100.

        Checks: (a) the param exists and is optional (required=false),
        and (b) config.max_rows == 100 (separate assertion on the QueryConfig
        field, not on QueryParamConfig).
        """
```

### WHAT — SQLite pragma verification test
```python
class TestSqlitePragmaBinding:
    def test_pragma_table_info_named_param(self, sqlite_db: Path) -> None:
        """Verify pragma_table_info(:table) works with named param binding."""
        # This validates the TOML SQL will work at runtime
```

## Part C: Package data config

### WHERE
- `pyproject.toml`

### WHAT — Add TOML to package data
```toml
[tool.setuptools.package-data]
"*" = ["py.typed", "*.toml"]
```

### HOW — Verify
- `load_default_queries()` test passes
- SQLite pragma binding test passes
- All existing tests still pass
- mypy, pylint pass
