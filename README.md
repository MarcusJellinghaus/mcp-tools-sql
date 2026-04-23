# mcp-tools-sql

> **Status: Under active development — not yet functional.**

An MCP server for safe, configurable SQL database access. Exposes schema introspection, user-defined SELECT queries, and structured UPDATE operations as MCP tools for LLM-assisted workflows.

## Key Ideas

- **Configurable, not ad-hoc**: Every query the LLM can run is defined upfront in config. The config is the security boundary.
- **Schema discovery**: Built-in tools to explore schemas, tables, columns, and foreign key relations.
- **Structured updates**: UPDATE operations are defined as table + key + fields, not raw SQL. The server generates the SQL.
- **Split config**: Query definitions live in the project repo (safe to commit). Credentials live in the user's home directory (never committed).
- **Multi-backend**: MS SQL Server (primary), PostgreSQL, SQLite.

## Architecture

```
MCP Client (Claude Code, etc.)
    ↕ STDIO/MCP
mcp-tools-sql server
    ├── Built-in tools (schema introspection)
    ├── Configured query tools (from mcp-tools-sql.toml)
    ├── Configured update tools (from mcp-tools-sql.toml)
    └── Backend abstraction
         ├── SQLite (stdlib)
         ├── MS SQL Server (pyodbc)
         └── PostgreSQL (psycopg)
```

See [docs/architecture/architecture.md](docs/architecture/architecture.md) for details.

## Installation

```bash
pip install mcp-tools-sql              # core + SQLite
pip install mcp-tools-sql[mssql]       # + SQL Server support
pip install mcp-tools-sql[postgresql]  # + PostgreSQL support
```

## Quick Start

```bash
# Generate starter config
mcp-tools-sql init --backend sqlite --output mcp-tools-sql.toml

# Validate setup
mcp-tools-sql verify --config mcp-tools-sql.toml

# Start MCP server
mcp-tools-sql --config mcp-tools-sql.toml
```

## Configuration

Two config files:

| File | Purpose | Location |
|------|---------|----------|
| `mcp-tools-sql.toml` | Query/update definitions | Project dir (committed) |
| `~/.mcp-tools-sql/config.toml` | Database connections + credentials | User home (never committed) |

See the [planning document](mcp-tools-sql.md) for full details.

## License

MIT
