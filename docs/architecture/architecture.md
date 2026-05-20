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
| `main.py` | CLI: argparse, logging, subcommands (server/init/verify) |
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

---

## 6. Cross-cutting Concerns

### Logging
- stdlib `logging` with structlog JSON backend (via mcp-coder-utils)
- `@log_function_call` decorator for timing and parameter capture

### Architecture Enforcement
- `tach.toml` — module boundary enforcement
- `.importlinter` — import contract validation

### Security
- Credentials in user config (`~/`), never in project repo
- Parameterized queries only — no string interpolation
- UPDATE requires unique key — prevents mass updates
- Row limits on all results — prevents context overflow
