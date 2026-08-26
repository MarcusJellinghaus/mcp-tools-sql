# mcp-tools-sql Architecture

**Framework**: Arc42 | **Version**: 0.1 | **Status**: Under active development
**Maintainer**: Marcus Jellinghaus

---

## 1. Introduction & Goals

### Purpose

MCP server providing safe, configurable SQL database access for LLM-assisted workflows. All queries are defined in config — no ad-hoc SQL execution.

### Key Quality Goals

- **Safety**: Config-driven queries, parameterized execution, no SQL injection
- **Discoverability**: Schema introspection with search/filter for wide tables
- **LLM-friendliness**: Truncated, formatted output that fits context windows
- **Multi-backend**: SQLite, MS SQL Server, PostgreSQL behind a common abstraction

### Stakeholders

- **LLM clients**: Claude Code, Claude Desktop, VSCode, mcp-coder — primary consumers
- **Data analysts**: Configure queries and deploy the server

---

## 2. Architecture Constraints

- Python 3.11+
- MCP protocol via STDIO transport (FastMCP)
- Pydantic for all models (config, dynamic tool params, internal)
- Three config files: `pyproject.toml` (dev), `~/.mcp-tools-sql/config.toml` (connections), `mcp-tools-sql.toml` (queries)

---

## 3. Context & Scope

```
┌─────────────────┐    STDIO/MCP     ┌──────────────────┐    DB driver   ┌─────────────┐
│   MCP Client    │◄────────────────►│  mcp-tools-sql   │───────────────►│  Database   │
│                 │                  │                  │                │             │
│ • Claude Code   │                  │  Built-in tools: │                │ • SQLite    │
│ • Claude Desktop│                  │   schema intro.  │                │ • SQL Server│
│ • VSCode        │                  │  Configured tools│                │ • PostgreSQL│
└─────────────────┘                  │   queries/updates│                └─────────────┘
                                     └──────────────────┘
                                              │
                                         reads config
                                              │
                                      ┌──────────────┐
                                      │ Config files │
                                      │ • queries    │
                                      │ • connections│
                                      └──────────────┘
```

---

## 4. Building Block View

### Layer Architecture

```
┌─────────────────────────────────────────────────────┐
│  Entry Point Layer                                  │
│  └── mcp_tools_sql.main                             │
├─────────────────────────────────────────────────────┤
│  CLI Layer                                          │
│  └── mcp_tools_sql.cli (init, verify subcommands)   │
├─────────────────────────────────────────────────────┤
│  Server Layer                                       │
│  └── mcp_tools_sql.server                           │
├─────────────────────────────────────────────────────┤
│  Tool Layer                                         │
│  ├── mcp_tools_sql.schema_tools                     │
│  ├── mcp_tools_sql.query_tools                      │
│  ├── mcp_tools_sql.update_tools                     │
│  └── mcp_tools_sql.validation_tools                 │
├─────────────────────────────────────────────────────┤
│  Verification Layer                                 │
│  └── mcp_tools_sql.verification (subpackage)        │
├─────────────────────────────────────────────────────┤
│  Infrastructure Layer                               │
│  ├── mcp_tools_sql.backends (sqlite, mssql, pg)     │
│  └── mcp_tools_sql.formatting                       │
├─────────────────────────────────────────────────────┤
│  Config Layer                                       │
│  └── mcp_tools_sql.config (models, loader)          │
├─────────────────────────────────────────────────────┤
│  Utilities Layer                                    │
│  └── mcp_tools_sql.utils                            │
└─────────────────────────────────────────────────────┘
```

**Dependency rules** (enforced by `.importlinter` and `tach.toml`):
- Each layer may only depend on layers below it
- Backend modules may NOT depend on each other
- `utils` has no upward dependencies

### CLI Layer (`mcp_tools_sql.cli`)

The `cli` package sits between `main` and `server` in the layered import contract.
It hosts the non-server subcommands (`init`, `verify`) under `cli/commands/`,
plus shared argparse helpers (`HelpHintArgumentParser`, `WideHelpFormatter`) in
`cli/parsers.py`. `cli` may import from `config`, `utils`, `backends`,
`schema_tools`, and `formatting`. It is the **only** layer between `main` and
`server` — `main` dispatches to either `cli` (for `init`/`verify`) or `server`
(for the default MCP-server command).

### Verification Layer (`mcp_tools_sql.verification`)

The verification engine was extracted from `cli/commands/verify.py` in
issue #21 to keep the CLI module under the 600-line file-size limit and
to make the engine reusable from non-CLI consumers (planned: MCP-server
health endpoint, programmatic validation in tests). The orchestrator
`verify_all(config_path, db_config_path)` composes every section in a
canonical order and returns `(sections, skip_summary)`; the CLI shim
is a pure printer that iterates `sections` as-is. The subpackage sits
at the `tool_implementation` layer (same as `schema_tools`/`query_tools`)
in `tach.toml`, and on its own line in `.importlinter` (above
`schema_tools|...`) because it imports from `schema_tools.load_default_queries`
and `query_helpers.extract_sql_params`.

### Key Modules

| Module | Responsibility |
|--------|---------------|
| `main.py` | CLI: argparse, per-command logging setup (level + file resolution), subcommands (server/init/verify) |
| `server.py` | Creates FastMCP, registers tools, starts STDIO transport |
| `schema_tools.py` | Built-in introspection: schemas, tables, columns, relations |
| `query_tools.py` | Dynamic registration of configured SELECT tools |
| `update_tools.py` | Dynamic registration of configured UPDATE tools |
| `validation_tools.py` | SQL validation via EXPLAIN |
| `config/models.py` | Pydantic models for all config |
| `config/loader.py` | TOML loading, validation, connection resolution |
| `backends/base.py` | `DatabaseBackend` ABC + factory |
| `backends/sqlite.py` | SQLite implementation |
| `backends/mssql.py` | SQL Server implementation (pyodbc) |
| `formatting.py` | Result → LLM-friendly text (tabular, truncated) |
| `tool_logging.py` | Per-tool-call logging context manager (INFO counts, DEBUG params, ERROR duration) |
| `verification/` | Verifier engine: environment, config, dependencies, builtin, connection, queries, updates. Orchestrated by `verify_all`. Consumed by the `verify` CLI subcommand. |

---

## 5. Dynamic Tool Registration

Configured queries/updates become MCP tools at server startup via `mcp.add_tool()`. Parameter schemas are generated at runtime using Pydantic `create_model()`.

Tool naming convention:
- `query_<name>` — configured SELECT tools
- `update_<name>` — configured UPDATE tools
- No prefix — built-in tools (read_schemas, read_tables, etc.)

### Multi-connection / multi-database routing (two-axis model)

Routing has two independent axes: a **connection** (server + backend +
credentials) and, within it, a **database** (catalog). The unit of execution is
a `(connection, database)` **target**, built by copying the connection config
with `database` set to the chosen catalog — so the four `INFORMATION_SCHEMA`
builtins and any configured SQL run verbatim against the right catalog with no
SQL rewriting. `config` resolves the config-order list of targets
(`resolve_targets` → `ResolvedTargets`); `backends/registry.py` lazily
instantiates and caches one backend per target and owns `close_all()` (kept in
`backends` to respect the `config`-may-not-import-`backends` contract). The
server builds both and closes the registry in a `finally`.

The tool surface is **conditional** and byte-identical for single-target
installs:

- A `connection` parameter is added to the read-only schema builtins only when
  more than one connection is configured; a `database` parameter and the
  config-only `read_databases` tool are added only when more than one target
  exists. Both parameters are keyword-only with a runtime-built `Literal` enum
  of the legal names.
- `database = "*"` fans out a schema builtin across every database of the
  selected connection (correctness path only — fetch-all, merge in config order,
  truncate at the end). Merged rows carry a `_database` source column and a
  per-database footer breakdown on truncation. There is no `connection = "*"`.
- `read_databases` is named for its result (the list of routable databases),
  matching the `read_*` builtin family; it reads config only and touches no
  database.
- `[queries.*]` / `[updates.*]` may pin `connection` / `database`, so
  `query_*` / `update_*` bind their target at registration and take no runtime
  routing params. `validate_sql` / `count_records` resolve backend and dialect
  per call from a runtime `database` param.

**Security note (decision 26).** The `databases` list is a routing/discovery
list, **not** an authorization boundary. A connection still reaches any catalog
its login can see (three-part `db.schema.table` names work verbatim), so
least-privilege must be enforced with per-connection database credentials at the
server — not by editing `databases`.

---

## 6. Cross-cutting Concerns

### Logging
- stdlib `logging` with structlog JSON backend (via mcp-coder-utils)
- `@log_function_call` decorator for timing and parameter capture
- **Two sinks with independent thresholds**: a JSON file at the resolved
  `--log-level`, plus a plain-text stderr console at `OUTPUT`
- **Per-command defaults**: `server` → `INFO` + a per-launch file under
  `~/.mcp-tools-sql/logs/`; `init`/`verify` → `OUTPUT`, console only.
  Resolved by the pure helpers `_resolve_log_level` / `_resolve_log_file` in
  `main.py`
- `--console-only` suppresses the file and takes precedence over `--log-file`
- Server startup failures go through `logger.error` (always recorded) plus an
  `OUTPUT`-level hint, following `mcp_coder`'s CLI convention
- Paths under the user home come from `utils/user_app_data.py`

### Architecture Enforcement
- `tach.toml` — module boundary enforcement
- `.importlinter` — import contract validation

### Security
- Credentials in user config (`~/`), never in project repo
- Parameterized queries only — no string interpolation
- UPDATE requires unique key — prevents mass updates
- Row limits on all results — prevents context overflow
