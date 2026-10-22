"""`help config` topic — a self-contained configuration guide.

Written for humans and for LLMs driving the CLI: everything needed to go
from nothing to a working server, without reading the docs.
`tests/cli/test_help_config.py` fails when a config model field is missing
here, so keep this text in step with `mcp_tools_sql.config.models`.
"""

from __future__ import annotations

CONFIG_GUIDE = """\
mcp-tools-sql configuration
===========================

Two TOML files. Every SQL statement the server can run is declared up front;
the config is the security boundary.

  1. Project query config   which tools exist (queries, updates)
     Found via: --config PATH, else ./mcp-tools-sql.toml,
                else [tool.mcp-tools-sql] in ./pyproject.toml
     Safe to commit: no secrets, only a connection *name*.

  2. Database config        connections and credentials
     Found via: --database-config PATH, else ~/.mcp-tools-sql/config.toml
     Never commit. ${ENV_VAR} placeholders are expanded in every string
     value (only in this file); an unset variable is an error.

Paths are resolved from the current working directory. Pass --config and
--database-config before the subcommand:
  mcp-tools-sql --config ./mcp-tools-sql.toml verify

Setup steps
-----------
  mcp-tools-sql init --backend sqlite|mssql   write both starter files
  (edit the files)
  mcp-tools-sql verify                         which files were found, and
                                               whether configs, connectivity
                                               and every query check out
  mcp-tools-sql tool                           list the tools that register
  mcp-tools-sql tool <name> --help             one tool's parameters
  mcp-tools-sql tool <name> --flag value       call a tool

Database config (~/.mcp-tools-sql/config.toml)
----------------------------------------------
  [connections.<name>]        one block per server; <name> is referenced
                              by the project config's `connection`
    backend                   "sqlite" | "mssql"
                              ("postgresql" is accepted by the config but
                              has no backend yet)
    description               shown by the read_databases tool
    # sqlite
    path                      database file; ":memory:" is a new empty DB
                              on every connection
    # mssql
    host                      "server" or "server\\\\instance" (TOML-escaped)
    port                      leave unset for 1433 or named instances
    databases                 catalogs to route to: ["sales", "hr"], or a
                              table: {sales = {description = "..."}}
    default_database          used when a caller omits `database`;
                              defaults to the first of `databases`
    database                  legacy single-catalog form of `databases`
    username, password        SQL auth; use password = "${MSSQL_PASSWORD}"
    trusted_connection        true = Windows/Kerberos auth, no password
    driver                    default "ODBC Driver 18 for SQL Server"
    encrypt                   default true
    trust_server_certificate  default false; true for local/dev servers
                              without a valid TLS certificate

  [security]
    allow_updates             default true; false registers no update_* tools

`databases` routes and is listed for discovery; it does NOT restrict
access. The login's own grants are the permission boundary.

Example:
  [connections.default]
  backend = "mssql"
  host = "sqlhost"
  databases = ["sales"]
  trusted_connection = true
  trust_server_certificate = true

Project query config (mcp-tools-sql.toml)
-----------------------------------------
  connection = "<name>"       required; default connection for all tools

  [queries.<name>]            registers tool query_<name>
    description               tool description shown to the LLM
    sql                       one SELECT; bind params as :param_name.
                              Must be read-only or the tool is skipped.
    max_rows_default          default 100; rows returned when the caller
                              omits max_rows
    max_rows_hard             cap on max_rows; defaults to max_rows_default
    filter_column             adds a <column>_filter glob parameter
    connection, database      pin this tool to one target (optional)
  [queries.<name>.params.<param>]
    type                      "str" | "int" | "float" | "datetime"
    description
    required                  default true
  [queries.<name>.backends.<backend>]
    sql                       override `sql` for one backend
                              ("sqlite" | "mssql")

  [updates.<name>]            registers tool update_<name>
    description
    schema                    e.g. "dbo"; empty for sqlite
    table
    connection, database      pin this tool to one target (optional)
  [updates.<name>.key]        the row selector (WHERE key = value)
    field, type (default "int"), description
  [[updates.<name>.fields]]   one block per updatable column
    field, type (default "str"), description,
    required                  default false; omitted fields stay unchanged

Example:
  connection = "default"

  [queries.orders_by_customer]
  description = "Orders for one customer, newest first"
  sql = "SELECT id, placed_at, total FROM orders WHERE customer_id = :customer_id ORDER BY placed_at DESC"

  [queries.orders_by_customer.params.customer_id]
  type = "int"
  description = "Customer id"

  [updates.set_order_status]
  description = "Change an order's status"
  table = "orders"

  [updates.set_order_status.key]
  field = "id"

  [[updates.set_order_status.fields]]
  field = "status"
  description = "New status"

Built-in tools (no config needed): read_schemas, read_tables, read_columns,
read_relations, validate_sql, count_records, summarize_columns. With more
than one (connection, database) target they gain connection/database
parameters and read_databases is added.

Wiring into an MCP client: run `mcp-tools-sql` (no subcommand) as a stdio
server, preferably with an absolute --config path, because the client
decides the working directory. Example .mcp.json entry:
  "sql": {"command": "mcp-tools-sql",
          "args": ["--config", "/abs/path/mcp-tools-sql.toml"],
          "env": {"MSSQL_PASSWORD": "${MSSQL_PASSWORD}"}}
"""
