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
# Generate starter project query config (mcp-tools-sql.toml) and a
# database config skeleton at ~/.mcp-tools-sql/config.toml
mcp-tools-sql init --backend sqlite

# Edit ~/.mcp-tools-sql/config.toml and set the SQLite path, e.g.:
#     [connections.default]
#     backend = "sqlite"
#     path = "./mydb.db"

# Validate environment, configs, dependencies, and connectivity
mcp-tools-sql verify

# Start MCP server
mcp-tools-sql --config mcp-tools-sql.toml
```

See [docs/cli.md](docs/cli.md) for the full CLI reference (all flags,
example output, exit codes).

## Configuration

Two config files:

| File | Purpose | Location |
|------|---------|----------|
| `mcp-tools-sql.toml` | Query/update definitions | Project dir (committed) |
| `~/.mcp-tools-sql/config.toml` | Database connections + credentials | User home (never committed) |

The `--config` flag overrides the project query config path; the
`--database-config` flag overrides the database config path.

See the [planning document](mcp-tools-sql.md) for full details.

## License

MIT
