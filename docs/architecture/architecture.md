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
│  Server Layer                                       │
│  └── mcp_tools_sql.server                           │
├─────────────────────────────────────────────────────┤
│  Tool Layer                                         │
│  ├── mcp_tools_sql.schema_tools                     │
│  ├── mcp_tools_sql.query_tools                      │
│  ├── mcp_tools_sql.update_tools                     │
│  └── mcp_tools_sql.validation_tools                 │
├─────────────────────────────────────────────────────┤
│  Infrastructure Layer                               │
│  ├── mcp_tools_sql.backends (sqlite, mssql, pg)     │
│  ├── mcp_tools_sql.config (models, loader)          │
│  └── mcp_tools_sql.formatting                       │
├─────────────────────────────────────────────────────┤
│  Utilities Layer                                    │
│  └── mcp_tools_sql.utils                            │
└─────────────────────────────────────────────────────┘
```

**Dependency rules** (enforced by `.importlinter` and `tach.toml`):
- Each layer may only depend on layers below it
- Backend modules may NOT depend on each other
- `utils` has no upward dependencies

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
