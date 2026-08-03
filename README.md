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

### Multiple connections and databases

Routing has two axes: a **connection** (server + backend + credentials) and,
within it, one or more **databases** (catalogs). A connection lists its catalogs
with `databases` and picks a default with `default_database`:

| Key | Purpose |
|-----|---------|
| `[connections.<name>]` | One connection (server + backend + credentials). Add more blocks for more servers/backends. |
| `databases` | Catalogs this connection routes to, e.g. `["sales", "hr"]` (PostgreSQL: exactly one; legacy `database = "..."` still works). |
| `default_database` | Catalog used when the caller omits `database`. |

Single-connection, single-database installs behave exactly as before. When more
than one target exists, the built-in schema tools gain `connection` / `database`
parameters (plus `database = "*"` fan-out across a connection's catalogs) and a
`read_databases` tool lists the routable targets. `[queries.*]` / `[updates.*]`
may pin a `connection` / `database`. See
[docs/cli.md](docs/cli.md#the-two-axis-model-fan-out-and-pinned-targets) for the
full model.

> **Note:** `databases` is a routing/discovery list, **not** an authorization
> boundary — a connection still reaches any catalog its login is granted. Grant
> least privilege with per-connection database credentials at the server.

See the [planning document](mcp-tools-sql.md) for full details.

## License

MIT
