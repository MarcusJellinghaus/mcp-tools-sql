# mcp-tools-sql

[![CI](https://github.com/MarcusJellinghaus/mcp-tools-sql/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/MarcusJellinghaus/mcp-tools-sql/actions/workflows/ci.yml) [![PyPI](https://img.shields.io/pypi/v/mcp-tools-sql)](https://pypi.org/project/mcp-tools-sql/) [![Python](https://img.shields.io/python/required-version-toml?tomlFilePath=https://raw.githubusercontent.com/MarcusJellinghaus/mcp-tools-sql/main/pyproject.toml)](https://pypi.org/project/mcp-tools-sql/) [![License](https://img.shields.io/github/license/MarcusJellinghaus/mcp-tools-sql)](LICENSE)

[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff) [![mypy](https://img.shields.io/badge/mypy-strict-blue)](https://mypy.readthedocs.io/) [![pylint](https://img.shields.io/badge/linting-pylint-yellowgreen)](https://github.com/pylint-dev/pylint) [![architecture](https://img.shields.io/badge/architecture-enforced-blue)](docs/quality-and-security-checks.md#architecture)

[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/MarcusJellinghaus/mcp-tools-sql/badge)](https://scorecard.dev/viewer/?uri=github.com/MarcusJellinghaus/mcp-tools-sql)

An MCP server for safe, configurable SQL database access. Exposes schema introspection, user-defined SELECT queries, and structured UPDATE operations as MCP tools for LLM-assisted workflows.

## Key Ideas

- **Configurable, not ad-hoc**: Every query the LLM can run is defined upfront in config. The config is the security boundary.
- **Queries are read-only**: Each configured query's SQL is proved read-only before it is registered as a tool; a violating query is skipped with a warning. This is unconditional — `security.allow_updates` governs `updates.*` only.
- **Schema discovery**: Built-in tools to explore schemas, tables, columns, and foreign key relations.
- **Structured updates**: UPDATE operations are defined as table + key + fields, not raw SQL. The server generates the SQL.
- **Split config**: Query definitions live in the project repo (safe to commit). Credentials live in the user's home directory (never committed).
- **Multi-backend**: MS SQL Server (primary) and SQLite. PostgreSQL is planned:
  its config is accepted, but there is no backend implementation yet.

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

# Try the tools without an MCP client
mcp-tools-sql tool
mcp-tools-sql tool read_tables --help

# Start MCP server
mcp-tools-sql --config mcp-tools-sql.toml
```

`mcp-tools-sql help config` prints a complete guide to both config files —
enough for an LLM driving the CLI to set the server up on its own.

## Documentation

| Doc | Covers |
|-----|--------|
| [docs/configuration.md](docs/configuration.md) | Both config files: discovery, every key, examples, multiple databases |
| [docs/mcp-client-setup.md](docs/mcp-client-setup.md) | Wiring the server into Claude Code, Claude Desktop and other MCP clients |
| [docs/cli.md](docs/cli.md) | Every command and flag, example output, exit codes |
| [docs/architecture/architecture.md](docs/architecture/architecture.md) | Internals |
| [docs/quality-and-security-checks.md](docs/quality-and-security-checks.md) | CI quality and security checks, required repo settings |

## Logging

The MCP server writes structured JSON logs to a new
`~/.mcp-tools-sql/logs/mcp_tools_sql_<timestamp>.log` file on every launch —
MCP clients usually discard a server's stderr, so the file is the only durable
record. User-facing messages, warnings and errors still appear on the console.

```bash
mcp-tools-sql --log-file /var/log/mcp-tools-sql.log   # explicit file
mcp-tools-sql --console-only --log-level DEBUG        # no file, verbose stderr
```

`init` and `verify` log to the console only. See [docs/cli.md](docs/cli.md#logging)
for thresholds and per-command defaults.

## Configuration

Two config files:

| File | Purpose | Location |
|------|---------|----------|
| `mcp-tools-sql.toml` | Query/update definitions | Project dir (committed) |
| `~/.mcp-tools-sql/config.toml` | Database connections + credentials | User home (never committed) |

The query config may instead live in `[tool.mcp-tools-sql]` of the project's
`pyproject.toml`. `--config` and `--database-config` override both paths.

One connection can route to several databases (catalogs), and several
connections can be configured side by side. See
[docs/configuration.md](docs/configuration.md) for every key.

> **Note:** `databases` is a routing/discovery list, **not** an authorization
> boundary — a connection still reaches any catalog its login is granted. Grant
> least privilege with per-connection database credentials at the server.

## License

MIT
