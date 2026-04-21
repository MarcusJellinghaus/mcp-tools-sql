# mcp-tools-sql — Planning Document

**Status**: Draft / Brainstorm
**Date**: 2026-04-21
**Author**: Marcus Jellinghaus

---

## 1. Vision

An MCP server for SQL database operations, following the same architecture and conventions as `mcp-tools-py`. Exposes configurable SQL queries (SELECT, UPDATE) as MCP tools, plus schema introspection and query validation. Primary target: MS SQL Server, with PostgreSQL and SQLite as secondary backends.

Published to PyPI as `mcp-tools-sql`. Developed in Python.

---

## 2. Use Cases

### Primary Example: Financial Data (Bank Fundamentals)

This is the driving use case — it pushes every aspect of the design.

**Goal**: "Read the profit and loss of Bank A from the bank fundamentals database."

**The challenge**: The database has schemas with wide tables (~1000 columns), domain-specific naming, and the user doesn't know the exact column names or bank identifiers upfront.

The LLM needs to:
1. Find the right schema (e.g. `bank_fundamentals`)
2. Find the right table (e.g. `bank_data`)
3. Find relevant columns out of 1000+ (P&L-related: `net_income`, `operating_revenue`, ...)
4. Identify the right bank (by name, country)
5. Pull the actual data

This is a *discovery workflow* — a multi-step process where each tool call informs the next. See section 4.1 for how the introspection tools handle this, particularly `search_columns` for navigating wide tables.

### Second Example: Master Data Mapping (Interactive → Automated)

**Goal**: Build and maintain a mapping table that links identifiers across multiple master data tables.

Typical scenario: An entity (e.g. a company) exists in several systems — Provider A has one ID, Provider B another, an internal system a third. A mapping table ties them together. Today this is done manually or with brittle scripts.

**Workflow**:
1. **Configure lookup tools**: Define SELECT tools for each master data source (`find_provider_a_entity`, `find_provider_b_entity`, `find_internal_entity`) — search by name, country, partial match
2. **Configure an update tool**: Define an UPDATE on the mapping table — key is one entity ID, fields are the other system IDs
3. **Interactive prompting**: User tells the LLM "Link Company X across all three systems." The LLM:
   - Queries each master data table to find the entity
   - Presents candidates for confirmation ("Found 3 matches in Bloomberg — which one?")
   - Writes the mapping via the UPDATE tool
4. **Automation**: Once the interactive workflow is reliable, wrap it in automated prompting (via mcp-coder or similar) — feed a list of entities, let the LLM resolve and map them in batch

**What this pushes in the design**:
- Multiple configured queries working together in one workflow
- The LLM reasoning across results from different tools
- UPDATE tools used in a loop
- The path from interactive to automated — same tools, same config, different orchestration

### Why these examples matter

If the tool can handle bank fundamentals (wide tables, multi-step discovery) and master data mapping (cross-table lookups, interactive → automated), it can handle simpler scenarios easily. Design for the hard cases first.

---

## 3. Design Principles

- **Configurable = safe + flexible**: Every query the LLM can run is defined upfront in config. No ad-hoc SQL execution. The config is the security boundary.
- **Limited output to LLM**: Always filter and truncate. If a query returns more than N rows (default 100), truncate with a clear message. Prevents context window overload.
- **Paging / confirmation on large results**: Phase 3 stretch goal. For now, hard truncation with a warning ("showing 100 of 4,832 rows").

---

## 4. Key Features

### 4.1 Schema Introspection (Built-in Tools)

Built-in tools that work out of the box without user configuration:

| Tool | Arguments | Returns |
|------|-----------|---------|
| `read_schemas()` | — | List of schema names in the database |
| `read_tables(schema)` | schema name | List of table names in that schema |
| `read_columns(schema, table, filter?)` | schema, table, optional filter | Column name, type, nullable, description/comment |
| `search_columns(schema, table, pattern)` | schema, table, search pattern | Columns matching the pattern (name LIKE or regex) |
| `read_relations(schema, table)` | schema, table | FK relationships: parent table, parent column, child table, child column, constraint name |

#### Handling wide tables (100+ columns)

The bank fundamentals scenario (see section 2) reveals that `read_columns` returning 1000 rows is unusable. Strategy:

1. **`read_columns` with `filter` parameter**: Optional `filter` argument for column name pattern matching (`LIKE '%income%'` or `LIKE '%revenue%'`). Without filter, truncates at `max_rows` (default 100) with a warning: "Showing 100 of 1,042 columns. Use filter parameter to narrow results."

2. **`search_columns` tool**: Dedicated search — takes a pattern, returns only matching columns. Supports SQL LIKE patterns (`%profit%`, `%loss%`) and optionally comma-separated terms (`"profit, loss, revenue, income"`). Returns column name + type + description.

3. **Column grouping by prefix/suffix** (phase 2): Many wide tables use naming conventions like `pl_net_income`, `pl_operating_revenue`, `bs_total_assets`. A `read_column_prefixes(schema, table)` tool could return grouped counts: `pl_* (47 columns), bs_* (83 columns), ...` — letting the LLM navigate by category before drilling in.

#### Example: Bank fundamentals discovery workflow

```
LLM: read_schemas()                          → [..., "bank_fundamentals", ...]
LLM: read_tables("bank_fundamentals")       → ["bank_data", "insurance_data", ...]
LLM: read_columns("bank_fundamentals", "bank_data")
     → "Showing 100 of 1,042 columns. Use filter to narrow."
       (first 100 columns listed)
LLM: search_columns("bank_fundamentals", "bank_data", "%profit%,%loss%,%income%,%revenue%")
     → net_income (decimal), operating_revenue (decimal), 
       pre_tax_profit (decimal), total_interest_income (decimal), ...
       (27 columns matched)
LLM: [now knows which columns to use in a configured SELECT query]
```

For finding the right bank, the user configures a lookup query:
```toml
[tool.mcp-tools-sql.queries.find_banks]
description = "Search for banks by name and/or country"
sql = """
    SELECT BankID, BankName, Country
    FROM bank_fundamentals.bank_data
    WHERE BankName LIKE :name_pattern
      AND (:country IS NULL OR Country = :country)
    ORDER BY BankName
"""
max_rows = 50
```

The final data retrieval is also a configured query — the LLM uses the discovered column names and bank IDs to call it.

Implementation per backend:
- **MSSQL / PostgreSQL**: `INFORMATION_SCHEMA.SCHEMATA`, `INFORMATION_SCHEMA.TABLES`, `INFORMATION_SCHEMA.COLUMNS`
- **SQLite**: `pragma_table_info`, `sqlite_master`

**Configurable, not hardcoded**: These are shipped as *default configured queries* in a built-in config, not as hardcoded Python code. This means:
- They serve as the first real test case for the config-driven query system
- Users can override them (e.g. filter out system schemas) or disable them
- The implementation proves the config → tool pipeline works end-to-end before any user config is written

Shipped as default config (e.g. `default_queries.toml` bundled in the package), loaded unless overridden.

### 4.2 Configurable SELECT Statements

- User defines named SELECT queries in a configuration file
- Each query becomes an MCP tool with a descriptive name and docstring
- Queries use parameterized placeholders (prevents SQL injection)
- Parameters exposed as MCP tool arguments with types and descriptions
- Result truncation: configurable `max_rows` per query (default 100)
- Truncation message: "Showing 100 of N rows. Refine your query or increase max_rows."

### 4.3 Configurable UPDATE Statements

Table-oriented configuration — structured field definitions, not raw SQL:

```toml
[tool.mcp-tools-sql.updates.update_order_status]
description = "Update the status of an order"
schema = "dbo"
table = "Orders"

# Unique key — identifies the row to update.
# If no row matches, nothing is updated.
[tool.mcp-tools-sql.updates.update_order_status.key]
field = "OrderID"
type = "int"
description = "The order ID to update"

# Fields that can be updated
[[tool.mcp-tools-sql.updates.update_order_status.fields]]
field = "Status"
type = "str"
description = "New status value (e.g. 'shipped', 'cancelled')"

[[tool.mcp-tools-sql.updates.update_order_status.fields]]
field = "LastModified"
type = "datetime"
description = "Timestamp of the last modification"
```

Key properties:
- **Unique key required**: Every UPDATE identifies exactly one row via a key. 0 matches → no update + clear message. The key must uniquely identify a row.
- **Structured field definitions**: Each field has `field` (column name), `type`, and `description`. The description is passed to the LLM as the tool argument docstring — helps it understand valid values.
- **Generated SQL**: The server builds the `UPDATE ... SET ... WHERE ...` statement from config. No raw SQL for mutations.
- **Transaction-wrapped**: Each update runs in a single transaction. Reports affected row count.

### 4.4 Query Validation

- `validate_sql` tool: takes raw SQL, checks it via the database's EXPLAIN mechanism
- Uses `SET SHOWPLAN_TEXT ON` (SQL Server) / `EXPLAIN` (PostgreSQL) / `EXPLAIN QUERY PLAN` (SQLite)
- Reports whether the query is syntactically valid, shows execution plan
- Useful for verifying configured queries work before deploying config changes

### 4.5 Phase Roadmap

#### Phase 1 — Help to write & run configured queries

The MVP. Everything in sections 4.1–4.4 above:
- Schema introspection (read_schemas, read_tables, read_columns + filter, search_columns, read_relations)
- Configurable SELECT and UPDATE tools
- Query validation
- `init` and `verify` CLI commands
- SQLite + MSSQL backends

The LLM can explore a database, understand its structure, and execute pre-configured queries. The user writes the config, the tool makes it safe and accessible.

#### Phase 2 — Richer introspection

Enhance the discovery capabilities based on phase 1 learnings:
- **Views, stored procedures, functions, triggers**: `read_views(schema)`, `read_stored_procedures(schema)`, etc.
- **SQL Server extended properties**: Surface column/table descriptions via `sys.extended_properties`. PostgreSQL equivalent: `COMMENT ON` via `pg_description`.
- **Foreign key relations — schema-wide**: `read_all_relations(schema)` for a full relationship map.
- **Column grouping by prefix**: `read_column_prefixes(schema, table)` — navigate wide tables by category (`pl_* → 47 columns`).
- **PostgreSQL backend**
- Further enhancements driven by phase 1 usage.

#### Phase 3 — Data exploration & smart filtering

Move from "run configured queries" to "help explore and understand data." Focus on master data / string columns, not numeric analysis.

- **Smart filtering**: Tools that help the LLM understand what values exist in a column before querying. `read_distinct_values(schema, table, column, limit?)` — returns distinct values with counts. Essential for columns like `Country`, `Status`, `BankType` where the LLM needs to know valid filter values.
- **Data profiling**: `read_table_profile(schema, table)` — row count, column stats (distinct count, null count, sample values). Compact overview, not full data.
- **SQL-based aggregations**: Configured aggregate queries (`GROUP BY`, `COUNT`, `DISTINCT`) as tools. Lets the LLM summarize data without pulling all rows.
- **Result paging**: Cursor-based pagination for large result sets across multiple tool calls.
- **Query builder assistance**: LLM uses introspection + profiling to help draft new configured queries for the config file.

#### Long-term vision — Data analysis pipeline integration

The tool becomes the **data retrieval layer** in a larger analysis workflow:

```
[mcp-tools-sql]          [downstream scripts]        [output]
  schema discovery    →    Python/R analysis      →    reports
  data retrieval      →    pandas / polars         →    dashboards
  master data lookup  →    statistical models      →    notebooks
```

- mcp-tools-sql handles **exploration and retrieval** — the LLM navigates the database, understands the schema, pulls the right data
- Downstream scripts handle **computation** — statistical analysis, visualization, modeling
- The LLM orchestrates both: uses SQL tools to find and fetch data, then invokes analysis scripts with that data

This keeps mcp-tools-sql focused on what it's good at (safe, configured database access) while enabling more ambitious data workflows.

### 4.6 LLM-Assisted Config Authoring

The config will grow as more queries and updates are added. The LLM should be able to write and maintain it.

**What's needed:**

1. **Config schema as an MCP resource**: Expose a `read_config_schema()` tool that returns the full config format with field descriptions, types, and examples. The LLM reads this before writing config — no guesswork.

2. **Structured add/remove tools** (instead of raw file editing):
   - `add_query(name, description, sql, params, max_rows?)` — adds a SELECT query to the config
   - `add_update(name, description, schema, table, key, fields)` — adds an UPDATE definition
   - `remove_query(name)` / `remove_update(name)` — removes by name
   - `list_configured_tools()` — shows what's currently configured
   
   These are CLI commands (or MCP tools) that read the TOML, modify it structurally, and write it back. The LLM never needs to understand TOML syntax — it just passes structured arguments.

3. **Verify after edit**: After any config change, automatically run `verify` on the affected entry and report the result. The LLM gets immediate feedback: "Query `get_bank_pnl` added. Validation: [OK] SQL valid, [OK] params well-formed."

4. **Hot-reload** (phase 2): Signal the running MCP server to reload config without restart. Until then, the LLM can note that a server restart is needed after config changes.

**Typical LLM workflow:**
```
User: "Add a query to look up banks by country"
LLM:  read_config_schema()              → understands the format
LLM:  search_columns("bank_fundamentals", "bank_data", "%country%")
      → finds: Country (varchar), CountryCode (char(2))
LLM:  add_query(
        name="find_banks_by_country",
        description="Search for banks in a given country",
        sql="SELECT BankID, BankName, Country FROM bank_fundamentals.bank_data WHERE Country = :country ORDER BY BankName",
        params=[{"name": "country", "type": "str", "description": "Country name", "required": true}],
        max_rows=50
      )
      → "Query `find_banks_by_country` added. Verify: [OK]"
```

This turns config authoring from "edit a TOML file correctly" into "call a tool with structured arguments" — much more natural for an LLM.

### 4.7 Not In Scope (Decided)

- **Ad-hoc query execution**: No `run_select` or `run_update` with arbitrary SQL. All queries are configured upfront.
- **Numeric data analysis in SQL**: Heavy number crunching belongs in downstream scripts (Python/pandas), not in SQL tools.

---

## 5. Database Backend Support

| Backend | Priority | Python Driver | Notes |
|---------|----------|---------------|-------|
| MS SQL Server | Primary | `pyodbc` | Requires ODBC driver on host |
| PostgreSQL | Secondary | `psycopg[binary]` (psycopg3) | Pure-Python option available |
| SQLite | Secondary | `sqlite3` (stdlib) | No extra deps, great for testing |

---

## 6. Configuration Architecture

### Three Config Files — Three Purposes

| File | Purpose | Location | In repo? | Who writes it |
|------|---------|----------|----------|---------------|
| **`pyproject.toml`** | Development of mcp-tools-sql itself | Project root of mcp-tools-sql | Yes | Developer |
| **`~/.mcp-tools-sql/config.toml`** | Database connections + security settings | User home dir | Never | Developer (once per machine) |
| **`mcp-tools-sql.toml`** | Query/update tool definitions | Project dir of the *user's* project | Yes (no secrets) | Developer / LLM |

Each file has a different audience and lifecycle:

#### 1. `pyproject.toml` — Tool development config

Standard Python project config for developing mcp-tools-sql itself. Contains:
- Package metadata, dependencies, build system
- Tool configs: black, isort, pylint, mypy, ruff, pytest markers
- `[tool.mcp-coder]` section for mcp-coder integration during development

This is NOT read by the mcp-tools-sql server at runtime. It's only for development.

#### 2. `~/.mcp-tools-sql/config.toml` — Connections & security

Per-machine, per-user. Like `~/.ssh/config` — set up once, never committed.

```toml
# ~/.mcp-tools-sql/config.toml

# Named database connections
[connections.bank-prod]
backend = "mssql"
host = "sql-server-prod.internal"
port = 1433
database = "bank_fundamentals"
trusted_connection = true          # Windows auth — no password needed

[connections.bank-dev]
backend = "mssql"
host = "localhost"
port = 1433
database = "bank_fundamentals_dev"
username = "sa"
password = "DevPassword123!"        # OK here — this file is never in a repo

[connections.local-sqlite]
backend = "sqlite"
path = "C:/data/test.db"

# Security settings (phase 2/3)
# [security]
# allow_updates = true              # global kill switch for all UPDATE tools
# require_confirmation = ["*"]      # which update tools need confirmation
# allowed_query_configs = ["C:/projects/bank-analysis/mcp-tools-sql.toml"]
```

Contains:
- **Named connections**: backend, host, credentials. Referenced by name from query configs.
- **Security settings** (phase 2/3): Global switches for update permissions. Could restrict which query config files are allowed to define UPDATE tools — prevents a random config from writing to a production database.

#### 3. `mcp-tools-sql.toml` — Query & update definitions

Lives in the user's project directory. Defines what tools the LLM can use. Contains NO secrets.

```toml
# ~/projects/bank-analysis/mcp-tools-sql.toml

connection = "bank-prod"           # references a named connection from config.toml

[queries.get_orders_by_customer]
description = "Retrieve orders for a given customer ID"
sql = """
    SELECT OrderID, OrderDate, TotalAmount
    FROM dbo.Orders
    WHERE CustomerID = :customer_id
    ORDER BY OrderDate DESC
"""
max_rows = 100

[queries.get_orders_by_customer.params.customer_id]
type = "int"
description = "The customer ID to look up"
required = true

[updates.update_order_status]
description = "Update the status of an order"
schema = "dbo"
table = "Orders"
# ... (see section 4.3 for full UPDATE config)
```

This file is safe to commit — it only contains query definitions and a connection *name*.

### File Format

TOML for all three. Considered YAML but TOML is:
- Already used by `pyproject.toml` (familiar to Python devs)
- Simpler than YAML (no indentation pitfalls)
- Has good Python support (`tomllib` in stdlib since 3.11, `tomli` for older)

### Authentication Methods (priority order)

| Method | Config in `config.toml` | When to use |
|--------|------------------------|-------------|
| **Trusted connection** (Windows Auth) | `trusted_connection = true` | Production / corporate. No password — uses Windows SSPI. Preferred for SQL Server. |
| **Password in config.toml** | `password = "..."` | Dev machines. Acceptable because file is in `~/`, never committed. |
| **Environment variable** | `credential_env_var = "DB_PASSWORD"` | CI/CD, Docker, shared machines. |
| **Connection string** | `connection_string = "..."` | Escape hatch for Azure AD, certificates, etc. Supports `${ENV_VAR}` substitution. |

### Security Rules

- **Query config (in repo)**: NEVER contains passwords, connection strings, or hostnames. Only a connection name.
- **User config (`~/`)**: MAY contain passwords. Per-machine, per-user, never committed. Treat it like `~/.ssh/config`.
- **`.gitignore`**: `init` adds `config.toml` and `connections.toml` patterns as safety net.
- **Verify command**: Warns if it detects credentials in the query config file.
- **Update security** (phase 2/3): User config can restrict which query configs are allowed to define UPDATE tools, and require confirmation for specific operations.

### Config Discovery

**Query config** (what tools to register):
1. `--config <path>` CLI flag
2. `mcp-tools-sql.toml` in project dir
3. `[tool.mcp-tools-sql]` in `pyproject.toml` of user's project (fallback, not the mcp-tools-sql dev pyproject)

**User config** (connections + security):
1. `--user-config <path>` CLI flag
2. `~/.mcp-tools-sql/config.toml`

---

## 7. Architecture

Following the mcp-tools-py pattern: layered architecture with clear module boundaries.

```
src/mcp_tools_sql/
├── __init__.py
├── __main__.py
├── main.py                    # CLI entry point (argparse, logging setup)
├── server.py                  # ToolServer: creates FastMCP, registers tools
├── config/
│   ├── __init__.py
│   ├── models.py              # Pydantic/dataclass models for config
│   └── loader.py              # Load & validate config from TOML/JSON
├── backends/
│   ├── __init__.py
│   ├── base.py                # Abstract base: connect, execute, explain
│   ├── mssql.py               # pyodbc implementation
│   ├── postgresql.py          # psycopg implementation
│   └── sqlite.py              # sqlite3 implementation
├── schema_tools.py            # Built-in: read_schemas, read_tables, read_columns
├── query_tools.py             # Register configured SELECT tools
├── update_tools.py            # Register configured UPDATE tools
├── validation_tools.py        # validate_sql tool
├── formatting.py              # Result → LLM-friendly text (tabular, truncated)
├── utils/
│   ├── __init__.py
│   └── log_utils.py           # Thin shim over mcp-coder-utils
└── py.typed
```

### Layer Rules

1. **Entry Point** (`main.py`) → **Server** (`server.py`) → **Tools** (`schema_tools`, `query_tools`, `update_tools`, `validation_tools`)
2. **Tools** → **Backends** (via abstract interface) + **Config** + **Formatting**
3. **Backends** → only stdlib + driver libraries
4. Backends MUST NOT depend on each other
5. `utils` has no upward dependencies

### Key Design Decisions

- **Backend abstraction**: `DatabaseBackend` ABC with `connect()`, `execute_query()`, `execute_update()`, `explain()`, `read_schemas()`, `read_tables()`, `read_columns()` methods.
- **Parameterized queries only**: All user-supplied values go through parameterized queries. No string interpolation.
- **UPDATE SQL is generated**: The server builds UPDATE statements from structured config — the user never writes raw SQL for mutations.

### Terminology

The config defines **queries** (SELECT) and **updates** (UPDATE). At runtime, each becomes an **MCP tool** — that's the MCP protocol term. In this document:

| Term | Meaning |
|------|---------|
| **Query** | A configured SELECT statement in the config file |
| **Update** | A configured UPDATE definition (table + key + fields) in the config file |
| **Tool** | What the LLM sees and calls — the MCP protocol concept. Each query/update becomes one tool. |
| **Built-in tool** | Schema introspection and validation tools that ship with the server |
| **Configured tool** | A tool created from user config (query or update) |

We avoid "view" (overloaded with SQL views) and "command" (overloaded with CLI).

### Dynamic Tool Registration

The number of MCP tools depends on the config. A config with 3 queries and 2 updates produces 5 configured tools (plus the built-in introspection tools). This is resolved at server startup.

**FastMCP supports this** via `mcp.add_tool(fn, name=..., description=...)`. Verified: name and description can be set at runtime.

#### How it works

At startup, for each configured query:

```python
# Pseudocode — server.py at startup
for name, query_config in config.queries.items():
    # 1. Build a function with the right signature
    tool_fn = build_query_function(name, query_config, backend)
    
    # 2. Register it as an MCP tool with dynamic name + description
    mcp.add_tool(
        fn=tool_fn,
        name=f"query_{name}",               # e.g. "query_find_banks_by_country"
        description=query_config.description  # from config
    )
```

#### Dynamic parameters

FastMCP infers the parameter schema from Python function type hints. It does NOT accept a custom JSON schema dict. So we need to **generate typed Python functions** from config:

```python
def build_query_function(name: str, config: QueryConfig, backend: DatabaseBackend):
    """Generate a typed function from a query config."""
    
    # Option A: Fixed signature with **kwargs (simple, less LLM-friendly)
    # The LLM sees generic params, relies on description for guidance
    def tool_fn(**kwargs: str) -> str:
        return execute_and_format(config, backend, kwargs)
    
    # Option B: Dynamically build a function with proper type hints (better)
    # Use types.FunctionType or a factory to create a function whose
    # signature matches the config params. FastMCP picks up the types.
    # e.g. config has params: customer_id (int, required), country (str, optional)
    # → generated function: def fn(customer_id: int, country: str = None) -> str
    
    return tool_fn
```

**Option B is preferred** — proper type hints mean the LLM sees a clean tool schema with named, typed parameters. Pydantic model generation at runtime can achieve this:

```python
from pydantic import create_model

# Build a Pydantic model from config params
fields = {}
for param in config.params:
    python_type = TYPE_MAP[param.type]  # "int" → int, "str" → str
    if param.required:
        fields[param.name] = (python_type, ...)
    else:
        fields[param.name] = (python_type | None, None)

ParamModel = create_model(f"{name}_params", **fields)

# Use the model as the function's input type
def tool_fn(params: ParamModel) -> str:
    return execute_and_format(config, backend, params.model_dump())
```

**Spike needed**: Verify that FastMCP correctly picks up `create_model` types and generates the right JSON schema for the LLM. This is the critical technical risk in the design.

#### Dynamic docstrings

The LLM sees two things for each tool:
1. **Tool description** — set via `description=` in `add_tool()`. Comes directly from the config's `description` field.
2. **Parameter descriptions** — come from Pydantic `Field(description=...)`. Each config param has a `description` that becomes the field description in the JSON schema.

```python
from pydantic import Field, create_model

fields = {}
for param in config.params:
    python_type = TYPE_MAP[param.type]
    if param.required:
        fields[param.name] = (python_type, Field(description=param.description))
    else:
        fields[param.name] = (python_type | None, Field(default=None, description=param.description))

# Result: the LLM sees a tool with named, typed, described parameters
```

This is what the LLM sees in the tool listing:
```
Tool: query_find_banks_by_country
Description: "Search for banks in a given country"
Parameters:
  - country (string, required): "Country name"
  - max_results (integer, optional): "Maximum number of results to return"
```

#### What the LLM calls

Tool names follow a convention:
- `query_<name>` for configured SELECT tools
- `update_<name>` for configured UPDATE tools
- No prefix for built-in tools (`read_schemas`, `read_tables`, etc.)

This makes it clear to the LLM which tools come from config and which are built-in.

---

## 8. Dependencies

Clear separation between what's always needed, what's needed per database, and what's for development.

### Core (always installed)

```toml
dependencies = [
    "mcp>=1.3.0",
    "mcp[cli]>=1.3.0",
    "structlog>=24.5.0",
    "python-json-logger>=3.2.1",
    "mcp-coder-utils",              # shared logging utilities
    "tabulate>=0.9.0",              # result formatting
    "pydantic>=2.0",                # config validation
]
```

SQLite support is included (stdlib `sqlite3`) — always available, no extra install.

### Database backends (optional, install per need)

```toml
[project.optional-dependencies]
mssql = ["pyodbc>=5.0.0"]                    # pip install mcp-tools-sql[mssql]
postgresql = ["psycopg[binary]>=3.1.0"]      # pip install mcp-tools-sql[postgresql]
all-backends = ["pyodbc>=5.0.0", "psycopg[binary]>=3.1.0"]
```

**Note on pyodbc**: Requires an ODBC driver installed at the OS level (not just the Python package). On Windows: "ODBC Driver 18 for SQL Server" from Microsoft. On Linux: `msodbcsql18` package. The `verify` command checks for this.

### Development tools (for contributing to mcp-tools-sql itself)

```toml
[project.optional-dependencies]
dev = [
    "mcp-workspace",  "mcp-coder",   # MCP ecosystem
    "black", "isort",                 # formatting
    "pylint", "mypy", "ruff",         # linting / type checking
    "tach", "pycycle", "vulture",     # architecture enforcement
    "pydeps",                         # dependency graphs
    "pytest", "pytest-asyncio", "pytest-xdist",  # testing
]
```

### What `verify` checks for dependencies

The `verify` command reports dependency status per section:

```
[dependencies]
  mcp             = 1.3.2                  [OK]
  pydantic        = 2.6.1                  [OK]
  tabulate        = 0.9.0                  [OK]
  mcp-coder-utils = 0.1.4                  [OK]

[backend: mssql]
  pyodbc          = 5.1.0                  [OK]
  ODBC driver     = "ODBC Driver 18 for SQL Server"  [OK]

[backend: postgresql]
  psycopg         = not installed          [SKIP] not configured

[backend: sqlite]
  sqlite3         = 3.45.1 (stdlib)        [OK]
```

This eliminates trial-and-error: run `verify` once after install and know exactly what's missing.

---

## 9. CLI Interface

### MCP Server (default command)

```
mcp-tools-sql \
    --config mcp-tools-sql.toml \
    --log-level INFO \
    --log-file logs/mcp_tools_sql.log \
    --console-only
```

Or reading from `pyproject.toml`:

```
mcp-tools-sql \
    --project-dir /path/to/project \
    --log-level INFO
```

### Verify Command

```
mcp-tools-sql verify \
    --config mcp-tools-sql.toml
```

A CLI-only command (not an MCP tool) that validates the full setup without starting the server. Inspired by `mcp-coder verify`.

**Output mirrors the config structure** — sections in the verify output correspond to sections in the TOML config, so you can immediately see which part of your config has the problem:

```
$ mcp-tools-sql verify --config mcp-tools-sql.toml

[connection]
  backend = mssql                          [OK]
  driver  = pyodbc 5.1.0                   [OK]
  host    = localhost:1433                  [OK] connected
  database = adventureworks                [OK]
  credentials = env:MSSQL_PASSWORD         [OK] resolved
  permissions = SELECT 1                   [OK]

[queries.get_orders_by_customer]
  sql     = EXPLAIN valid                  [OK]
  params  = customer_id (int, required)    [OK]
  max_rows = 100                           [OK]

[queries.get_inventory_levels]
  sql     = EXPLAIN valid                  [OK]
  params  = warehouse_id (int, required)   [OK]
  max_rows = 50                            [OK]

[updates.update_order_status]
  table   = dbo.Orders                     [OK] exists
  key     = OrderID (int)                  [OK] column exists
  fields  = Status (str)                   [OK] column exists
  fields  = LastModified (datetime)        [WARN] column not found

Result: 11 checks passed, 1 warning, 0 errors
```

Each line shows the config key, its resolved value or check result, and a status label. Returns exit code 0 if no errors, 1 otherwise.

Checks performed per section:

| Config Section | Checks |
|---------------|--------|
| `[connection]` | Backend driver installed, connection succeeds, credentials resolve, read permission (`SELECT 1`) |
| `[queries.*]` | SQL valid (via EXPLAIN), parameters well-formed, max_rows set |
| `[updates.*]` | Table exists, key column exists, all field columns exist (via INFORMATION_SCHEMA) |

Use cases:
- **First-time setup**: run after `init` to catch typos, wrong column names, connection issues
- **CI/CD**: run in pipeline before deploying config changes to catch regressions
- **Debugging**: when MCP tools return errors at runtime, verify narrows down the cause

### Init Command

```
mcp-tools-sql init \
    --backend mssql \
    --output mcp-tools-sql.toml
```

Generates a starter config file with:
- Connection section pre-filled for the chosen backend (mssql/postgresql/sqlite), with placeholder values and comments
- One example SELECT query (commented out)
- One example UPDATE definition (commented out)
- The default schema introspection queries (active)

```toml
# Generated by: mcp-tools-sql init --backend mssql
# Documentation: https://github.com/MarcusJellinghaus/mcp-tools-sql

[connection]
backend = "mssql"
host = "localhost"
port = 1433
database = "mydb"                    # ← change this
username = "sa"                      # ← change this
credential_env_var = "MSSQL_PASSWORD" # set this env var with your password

# --- Example SELECT query (uncomment and adapt) ---
# [queries.get_customers]
# description = "Look up customers by name"
# sql = """
#     SELECT CustomerID, Name, Email
#     FROM dbo.Customers
#     WHERE Name LIKE :search_pattern
#     ORDER BY Name
# """
# max_rows = 100
#
# [queries.get_customers.params.search_pattern]
# type = "str"
# description = "Search pattern (use % as wildcard)"
# required = true

# --- Example UPDATE definition (uncomment and adapt) ---
# [updates.update_customer_email]
# description = "Update a customer's email address"
# schema = "dbo"
# table = "Customers"
#
# [updates.update_customer_email.key]
# field = "CustomerID"
# type = "int"
# description = "The customer ID"
#
# [[updates.update_customer_email.fields]]
# field = "Email"
# type = "str"
# description = "New email address"
```

After generating, the natural next step is `mcp-tools-sql verify` to test the connection.

Flags:
- `--backend mssql|postgresql|sqlite` — pre-fills connection defaults for that backend
- `--output <path>` — output file (default: `mcp-tools-sql.toml`)
- `--pyproject` — instead of standalone file, append to existing `pyproject.toml` under `[tool.mcp-tools-sql]`

### MCP Client Configuration (`.mcp.json`)

```json
{
  "tools-sql": {
    "type": "stdio",
    "command": "${MCP_CODER_VENV_PATH}\\mcp-tools-sql.exe",
    "args": [
      "--project-dir", "${MCP_CODER_PROJECT_DIR}",
      "--log-level", "INFO"
    ],
    "env": {
      "MSSQL_PASSWORD": "${MSSQL_PASSWORD}"
    }
  }
}
```

---

## 10. Testing Strategy

### 9.1 Unit Tests (No Database Required)

- Config loading and validation
- SQL generation from UPDATE config (field definitions → UPDATE statement)
- Parameter binding logic
- Result formatting / truncation
- Backend selection logic
- Error handling paths

These run everywhere — local, CI, GitHub Actions.

### 9.2 SQLite Integration Tests

**This is the core of the testing strategy for CI.**

SQLite needs no external service. Tests can:
- Create an in-memory or temp-file database
- Set up schema + seed data in a pytest fixture
- Run the full tool pipeline: config → backend → execute → format
- Validate parameterized queries, row limits, error handling
- Test schema introspection tools
- Test the `validate_sql` tool (SQLite supports `EXPLAIN QUERY PLAN`)
- Test UPDATE tools: key lookup, field update, affected row count

```python
@pytest.fixture
def sqlite_backend(tmp_path):
    """Create a SQLite database with test data."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id INT, status TEXT)")
    conn.execute("INSERT INTO orders VALUES (1, 100, 'pending')")
    conn.commit()
    conn.close()
    return SQLiteBackend(connection_string=str(db_path))
```

**Markers**: `@pytest.mark.sqlite_integration` — always runs in CI.

### 9.3 PostgreSQL Integration Tests (GitHub Actions)

GitHub Actions supports PostgreSQL as a service container — free and straightforward:

```yaml
services:
  postgres:
    image: postgres:16
    env:
      POSTGRES_PASSWORD: testpass
      POSTGRES_DB: testdb
    ports:
      - 5432:5432
    options: >-
      --health-cmd pg_isready
      --health-interval 10s
      --health-timeout 5s
      --health-retries 5
```

- Tests create schema, run queries, validate results
- **Marker**: `@pytest.mark.postgresql_integration`
- Runs in CI matrix alongside SQLite tests

### 9.4 MS SQL Server Integration Tests

**Challenge**: No free MS SQL Server container in GitHub Actions (Linux runners can use `mcr.microsoft.com/mssql/server` but it requires accepting EULA and uses ~2GB RAM).

**Options**:

| Option | Feasibility | Notes |
|--------|-------------|-------|
| SQL Server 2022 Linux container in GH Actions | Possible | `mcr.microsoft.com/mssql/server:2022-latest`, needs `ACCEPT_EULA=Y`, 2GB+ RAM |
| Skip in CI, run locally only | Simplest | Mark as `@pytest.mark.mssql_integration`, skip by default |

**Recommendation**: Start with the Linux container — it works on ubuntu runners. Fall back to "skip in CI" if too slow or flaky.

```yaml
services:
  mssql:
    image: mcr.microsoft.com/mssql/server:2022-latest
    env:
      ACCEPT_EULA: "Y"
      SA_PASSWORD: "TestPassword123!"
    ports:
      - 1433:1433
```

**Marker**: `@pytest.mark.mssql_integration`

### 9.5 Test Matrix Summary

| Test Type | Local | GitHub Actions | Database |
|-----------|-------|----------------|----------|
| Unit tests | Always | Always | None |
| SQLite integration | Always | Always | In-memory |
| PostgreSQL integration | Optional | Always (service container) | Container |
| MS SQL Server integration | Optional | Best-effort (service container) | Container |

---

## 11. Security Considerations

- **Split config** — credentials in `~/.mcp-tools-sql/connections.toml` (never in repo), queries in project dir (committed)
- **Parameterized queries only** — no string formatting/interpolation for user values
- **No ad-hoc SQL** — all queries/updates are configured upfront
- **UPDATE requires unique key** — prevents accidental mass updates
- **Connection string sanitization** — never log passwords
- **Row limits** — prevent large result sets from overloading LLM context

---

## 12. Project Setup Checklist

Following `docs/repository-setup/` (note: setup docs need updating, see mcp_coder issue).

**Repository basics:**
- [ ] GitHub repo: `MarcusJellinghaus/mcp-tools-sql`
- [ ] `LICENSE` (MIT)
- [ ] `.gitignore` (Python + `connections.toml` safety net)
- [ ] `.gitattributes`

**Python project:**
- [ ] `pyproject.toml` with setuptools-scm, tool configs (black, isort, pylint, mypy, ruff)
- [ ] src-layout: `src/mcp_tools_sql/`
- [ ] `.importlinter` + `tach.toml` for architecture enforcement
- [ ] Dependency: `mcp-coder-utils` (shared logging/subprocess)

**Claude Code setup:**
- [ ] `.claude/CLAUDE.md` — project conventions, tool mapping, allowed bash commands
- [ ] `.claude/settings.local.json` — MCP tool permissions, skill permissions, enabled MCP servers
- [ ] `.claude/skills/` — workflow skills deployed via `mcp-coder init` (issue lifecycle, implementation, review, commit, rebase, etc.)
- [ ] `.claude/agents/commit-pusher.md` — commit agent definition
- [ ] `.claude/knowledge_base/` — planning principles, Python conventions, refactoring principles
- [ ] `.mcp.json` — MCP servers: mcp-tools-py (code quality), mcp-workspace (file ops + reference projects)

**GitHub:**
- [ ] `.github/workflows/ci.yml` with test matrix (unit + SQLite + PostgreSQL + MSSQL)
- [ ] `.github/workflows/publish.yml` for PyPI releases
- [ ] `.github/dependabot.yml`
- [ ] GitHub workflow labels via `mcp-coder gh-tool define-labels`

**Documentation:**
- [ ] `docs/architecture/architecture.md` (Arc42)

---

## 13. Open Questions

### Decided (closed)

- ~~**Config format**~~: Three files. `pyproject.toml` (dev only), `~/.mcp-tools-sql/config.toml` (connections + security), `mcp-tools-sql.toml` (query definitions). See section 6.
- ~~**mcp-coder integration**~~: Standalone MCP server. mcp-coder is used to develop this tool, not to integrate with it.
- ~~**Dynamic tool naming**~~: FastMCP supports `mcp.add_tool(fn, name=..., description=...)`. Remaining `create_model` risk is an M1 spike.

### Phase 0 — Decide before starting implementation

1. ~~**Pydantic vs dataclasses**~~: Decided — Pydantic for everything. Already a hard dependency for `create_model` (dynamic tool params). One model library for config validation, TOML loading, dynamic schemas, and internal models.

2. ~~**ODBC driver strategy**~~: Decided — pyodbc only. Document the OS-level ODBC driver requirement, `verify` checks for it. pymssql not needed (lacks trusted connection support).

3. ~~**Repo name / package name**~~: Confirmed — `mcp-tools-sql` (PyPI/repo) / `mcp_tools_sql` (Python package).

### Phase 1 — Resolve during M1/M2

4. **`create_model` + FastMCP spike**: Verify Pydantic `create_model` types generate correct JSON schemas in FastMCP. Build a 20-line test. This is the critical technical risk.

5. **Connection pooling**: Connect-per-call or connection pool? For an MCP server (single LLM client, low concurrency), connect-per-call is likely fine. Revisit if performance is an issue.

6. **Transaction semantics for UPDATE**: Single auto-commit transaction per tool call. Confirm this is sufficient — no multi-statement transactions needed.

7. **Composite keys**: Should UPDATE support multi-column unique keys (composite primary key)? Or single-column only for MVP? → Leaning single-column for phase 1, composite in phase 2.

### Phase 3+

8. **Result pagination**: Cursor-based pagination across multiple tool calls for large result sets. Not needed until phase 3.

---

## 14. Milestones (Rough)

1. **M1 — Skeleton**: Repo setup, CI, config loading, SQLite backend, schema introspection tools
2. **M2 — SELECT tools**: Config-driven SELECT tool registration, parameterized queries, result formatting + truncation
3. **M3 — UPDATE tools**: Structured UPDATE config, SQL generation, unique key enforcement, transaction wrapping
4. **M4 — MS SQL Server**: pyodbc backend, connection config, MSSQL integration tests
5. **M5 — Validation**: `validate_sql` tool with EXPLAIN support per backend
6. **M6 — PostgreSQL**: psycopg backend, PostgreSQL integration tests
7. **M7 — PyPI**: First published release, README, documentation
