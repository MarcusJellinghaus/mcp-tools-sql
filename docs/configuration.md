# Configuration Reference

mcp-tools-sql reads two TOML files. Every SQL statement the server can run is
declared in them up front — the config is the security boundary.

| File | Defines | Default location | Commit it? |
|------|---------|------------------|------------|
| Project query config | Which tools exist: `[queries.*]`, `[updates.*]` | `./mcp-tools-sql.toml` | Yes — no secrets, only a connection *name* |
| Database config | Connections, credentials, `[security]` | `~/.mcp-tools-sql/config.toml` | Never |

`mcp-tools-sql help config` prints a condensed version of this page. It is
written so an LLM driving the CLI can set up the server without these docs.

## Workflow

```bash
mcp-tools-sql init --backend sqlite   # or mssql: writes both starter files
# edit the two files
mcp-tools-sql verify                  # resolved file paths, dependencies, connectivity, every query
mcp-tools-sql tool                    # the tools that will register
```

See [cli.md](cli.md) for each command's flags and output.

## Discovery

**Project query config**, first match wins:

1. `--config PATH`
2. `mcp-tools-sql.toml` in the current working directory
3. The `[tool.mcp-tools-sql]` table of `pyproject.toml` in the current working
   directory (written by `init --pyproject`). A `pyproject.toml` without that
   table is skipped.

`--config` may also point at a `pyproject.toml`; its `[tool.mcp-tools-sql]`
table is then read as the query config.

**Database config**:

1. `--database-config PATH`
2. `~/.mcp-tools-sql/config.toml`

Discovery is relative to the **working directory of the process**. MCP clients
choose that directory themselves, so pass an absolute `--config` in client
configs — see [mcp-client-setup.md](mcp-client-setup.md).

Both flags are global: put them before the subcommand
(`mcp-tools-sql --config x.toml verify`).

## Database config (`~/.mcp-tools-sql/config.toml`)

### `[connections.<name>]`

One block per server. `<name>` is what the project config's `connection` key
refers to.

| Key | Backends | Default | Meaning |
|-----|----------|---------|---------|
| `backend` | all | `"sqlite"` | `"sqlite"` or `"mssql"`. `"postgresql"` passes config validation but has no backend implementation yet — server and `tool` startup fail with `Unsupported backend` when a configured query or update targets it (backends are created during tool registration); otherwise the first built-in tool call fails. |
| `description` | all | `""` | Shown by the `read_databases` tool. |
| `path` | sqlite | `""` | Database file; relative paths resolve from the working directory. `":memory:"` opens a new, empty database on every connection (`verify` warns). |
| `host` | mssql | `""` | `"server"` or a named instance `"server\\instance"` — see [MSSQL host and port](#mssql-host-and-port). |
| `port` | mssql | unset | Only for a fixed non-default TCP port. |
| `databases` | mssql | `[]` | Catalogs this connection routes to — see [Multiple databases](#multiple-connections-and-databases). |
| `default_database` | mssql | first of `databases` | Used when a caller omits `database`. Must be one of `databases`. |
| `database` | mssql | `""` | Legacy single-catalog form of `databases`. Must agree with `databases`/`default_database` if both are set. |
| `username`, `password` | mssql | `""` | SQL authentication. Use `${VAR}` for the password. |
| `trusted_connection` | mssql | `false` | Windows (SSPI) or Kerberos authentication; no password. |
| `driver` | mssql | `"ODBC Driver 18 for SQL Server"` | ODBC driver name. |
| `encrypt` | mssql | `true` | ODBC `Encrypt=`. |
| `trust_server_certificate` | mssql | `false` | ODBC `TrustServerCertificate=`. Set `true` for local or dev servers without a valid TLS certificate, or the driver refuses the connection. |

An mssql connection needs at least one database.

### `[security]`

| Key | Default | Meaning |
|-----|---------|---------|
| `allow_updates` | `true` | `false` registers no `update_*` tools. Configured queries are always read-only, whatever this is set to. |

### Environment variables

Any string value in the database config may contain `${NAME}`; it is replaced
with the environment variable at load time. An unset variable is an error
(`verify` reports it in the `database_config_parse` row). Substitution happens
only in this file — never in the project config or in SQL.

### Authentication

| Method | Config | When |
|--------|--------|------|
| Trusted connection | `trusted_connection = true` | Corporate SQL Server. Preferred. On Linux, `verify` checks for a Kerberos ticket. |
| Password from the environment | `password = "${MSSQL_PASSWORD}"` | CI, containers, shared machines. |
| Password in the file | `password = "..."` | Dev machines only. The file lives in your home directory and is never committed. |

### MSSQL host and port

- **Default instance**: `host = "myserver"`, no `port`. ODBC uses 1433.
- **Named instance**: `host = "myserver\\instance"`, no `port`. SQL Browser
  (UDP 1434) resolves the port, as in SSMS.
- **Fixed non-default port**: `host = "myserver"`, `port = 14330`.

Don't combine `host\instance` with `port`: ODBC ignores the instance name and
connects to `host:port`, which usually times out.

TOML escaping: write `"myserver\\instance"` (basic string) or
`'myserver\instance'` (literal string). `"myserver\instance"` is invalid TOML,
and `\n` would silently become a newline.

### Examples

```toml
# SQLite
[connections.default]
backend = "sqlite"
path = "C:/data/app.db"            # forward slashes work on Windows too
```

```toml
# SQL Server, Windows authentication, two catalogs
[connections.default]
backend = "mssql"
host = "sqlprod\\reporting"
databases = ["sales", "hr"]
default_database = "sales"
trusted_connection = true

# SQL Server, SQL authentication, local container
[connections.dev]
backend = "mssql"
host = "localhost"
port = 14330
database = "sales_dev"
username = "sa"
password = "${MSSQL_PASSWORD}"
trust_server_certificate = true
```

## Project query config (`mcp-tools-sql.toml`)

| Key | Default | Meaning |
|-----|---------|---------|
| `connection` | — (required) | Name of the default connection in the database config. |

Credentials do not belong here: a `password` key logs a warning and `verify`
reports it.

### `[queries.<name>]` → tool `query_<name>`

| Key | Default | Meaning |
|-----|---------|---------|
| `description` | `""` | Tool description the LLM sees. |
| `sql` | — (required) | One `SELECT`. Bind parameters as `:param_name`. |
| `max_rows_default` | `100` | Rows returned when the caller omits `max_rows`. |
| `max_rows_hard` | `max_rows_default` | Upper bound on the caller's `max_rows`. |
| `filter_column` | `""` | Adds a `<column>_filter` parameter: a case-insensitive glob applied to that column of the result. |
| `connection`, `database` | `""` | Pin the tool to one target. Pinned tools take no runtime `connection`/`database` parameter. |

**Read-only gate.** At registration the SQL that will run on the tool's
backend — its `backends.<backend>` override if present, else `sql` — is
proved read-only. A query that fails is not registered and the server logs a
warning. `verify` additionally checks every `backends` override and reports a
failure as an error.

`[queries.<name>.params.<param>]` — one table per bind parameter:

| Key | Default | Meaning |
|-----|---------|---------|
| `type` | `"str"` | `"str"`, `"int"`, `"float"` or `"datetime"`. |
| `description` | `""` | Parameter description the LLM sees. |
| `required` | `true` | |

`[queries.<name>.backends.<backend>]` — `sql` override for one backend
(`sqlite` or `mssql`). Useful when one config serves several backends. Any
other key is dead config and `verify` warns.

### `[updates.<name>]` → tool `update_<name>`

Updates are structured, not SQL: the server generates
`UPDATE <schema>.<table> SET <fields> WHERE <key> = <value>` with bound values.
The key should be unique; if a call changes more than one row, the result
carries a warning (the rows stay changed).

| Key | Default | Meaning |
|-----|---------|---------|
| `description` | `""` | Tool description. |
| `schema` | `""` | e.g. `"dbo"`. Leave empty for SQLite. |
| `table` | — (required) | Target table. |
| `connection`, `database` | `""` | Pin the tool to one target. |

`[updates.<name>.key]` — the row selector:

| Key | Default |
|-----|---------|
| `field` | — (required) |
| `type` | `"int"` |
| `description` | `""` |

`[[updates.<name>.fields]]` — one block per updatable column:

| Key | Default | Meaning |
|-----|---------|---------|
| `field` | — (required) | Column name. |
| `type` | `"str"` | |
| `description` | `""` | |
| `required` | `false` | Optional fields left out of a call are not changed. |

`verify` checks that the table, key column and every field column exist.

### Example

```toml
connection = "default"

[queries.orders_by_customer]
description = "Orders for one customer, newest first"
sql = """
    SELECT id, placed_at, total
    FROM dbo.orders
    WHERE customer_id = :customer_id
    ORDER BY placed_at DESC
"""
max_rows_default = 50

[queries.orders_by_customer.params.customer_id]
type = "int"
description = "Customer id"

[updates.set_order_status]
description = "Change an order's status"
schema = "dbo"
table = "orders"

[updates.set_order_status.key]
field = "id"
description = "Order id"

[[updates.set_order_status.fields]]
field = "status"
description = "New status"
```

### In `pyproject.toml`

The same keys, nested under `[tool.mcp-tools-sql]`:

```toml
[tool.mcp-tools-sql]
connection = "default"

[tool.mcp-tools-sql.queries.orders_by_customer]
sql = "SELECT id FROM orders WHERE customer_id = :customer_id"
```

## Built-in tools

These register with no project config entries: `read_schemas`, `read_tables`,
`read_columns`, `read_relations`, `validate_sql`, `count_records`,
`summarize_columns`. The four `read_*` queries are defined in
`src/mcp_tools_sql/default_queries.toml`.

## Multiple connections and databases

Routing has two axes: a **connection** (server + backend + credentials) and,
within it, a **database** (catalog). Single-target installs see no extra
parameters.

- **Conditional parameters.** A `connection` parameter appears on the built-in
  schema tools when more than one connection is configured. A `database`
  parameter and the `read_databases` tool appear when more than one
  `(connection, database)` target exists. Both parameters only accept the
  configured names.
- **Fan-out.** The four `read_*` tools accept `database = "*"` to run across
  every database of the selected connection. Merged rows gain a `_database`
  column. There is no `connection = "*"`.
- **`read_databases`** lists the configured targets without touching a
  database, so a caller can find the legal `connection`/`database` values.
- **Pinned tools.** `query_*` and `update_*` tools resolve their target at
  registration (from their own `connection`/`database`, else the file default)
  and take no runtime target parameters. `validate_sql` and `count_records`
  keep a runtime `database` parameter.

`databases` can also be a table carrying descriptions:

```toml
[connections.prod]
backend = "mssql"
host = "sqlprod"
trusted_connection = true
default_database = "sales"

[connections.prod.databases]
sales = { description = "Orders and invoices" }
hr = { description = "Staff records" }
```

> **Not an authorization boundary.** `databases` controls routing and
> discovery only. A login can still reach any catalog it is granted —
> three-part `db.schema.table` names work regardless of this list. Grant least
> privilege on the server, per connection.
