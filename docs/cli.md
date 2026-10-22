# mcp-tools-sql CLI Reference

This document describes the `mcp-tools-sql` command-line interface
delivered by the package's console-script entry point. The config file
format is in [configuration.md](configuration.md); wiring the server into
an MCP client is in [mcp-client-setup.md](mcp-client-setup.md).

## Synopsis

```text
mcp-tools-sql [--config PATH] [--database-config PATH]
              [--log-level LEVEL] [--log-file PATH] [--console-only]
              [--version] [--help]
              [<command> [<args>]]
```

| Command | Purpose |
|---------|---------|
| *(none)*, `server` | Run the MCP server over stdio. |
| `help [config]` | Top-level help, or the config file guide. |
| `init` | Write starter config files. |
| `verify` | Check environment, configs, dependencies, connectivity and every configured tool. |
| `tool` | List, describe and call the MCP tools directly. |

## Global flags

These flags are accepted on the top-level `mcp-tools-sql` command and
apply to every subcommand. Subcommands MAY ignore flags that do not
apply to them (e.g. `init` does not consult `--config` or
`--database-config`). `--log-level` and `--log-file` are accepted
everywhere but **resolve differently per subcommand** — see
[Logging](#logging) below.

| Flag | Default | Description |
|------|---------|-------------|
| `--help`, `-h` | — | Print help for `mcp-tools-sql` (or for a subcommand when used as `<command> -h`) and exit 0. |
| `--version` | — | Print the installed package version and exit 0. |
| `--config PATH` | (auto-discovered) | Path to the project query config. Discovery falls back to `mcp-tools-sql.toml` in the current directory and then `[tool.mcp-tools-sql]` in `pyproject.toml` — see [Discovery](configuration.md#discovery). |
| `--database-config PATH` | `~/.mcp-tools-sql/config.toml` | Path to the database config (connections + credentials). |
| `--log-level LEVEL` | per command (see below) | One of `DEBUG`, `INFO`, `OUTPUT`, `WARNING`, `ERROR`. |
| `--log-file PATH` | per command (see below) | Write structured JSON logs to this file instead of the default path. Ignored when `--console-only` is set. |
| `--console-only` | off | Suppress the log file; send everything to stderr instead. |

### Logging

`mcp-tools-sql` writes to two sinks with independent thresholds:

| Sink | Format | Threshold |
|------|--------|-----------|
| Log file | structured JSON | the resolved `--log-level` |
| Console (stderr) | plain text | `OUTPUT` and above — user-facing messages, warnings, errors |

Defaults depend on the command:

| Command | `--log-level` | Log file |
|---------|---------------|----------|
| `server` | `INFO` | `~/.mcp-tools-sql/logs/mcp_tools_sql_<timestamp>.log` — a new file per launch |
| every other command | `OUTPUT` | none — console only |

`server` defaults to a file because MCP clients typically discard the server's
stderr, making the file the only durable record. A failed launch is logged at
`ERROR`, so the reason it failed is in the file at every `--log-level`. Log
files are never rotated or deleted, and the server will fail to start if
`~/.mcp-tools-sql/logs/` cannot be created.

`--log-level` sets the **file** threshold. The console stays at `OUTPUT`
whenever a log file is in use. To get detailed output inline, use
`--console-only`: it suppresses the file and sends everything at the resolved
`--log-level` to stderr. `--console-only` takes precedence over `--log-file`.

## Commands

### `init` — scaffold starter configs

```text
mcp-tools-sql init --backend {sqlite|mssql|postgresql}
                   [--output PATH]
                   [--pyproject]
```

Scaffolds two files:

1. A project query config (default `./mcp-tools-sql.toml`, or — with
   `--pyproject` — a `[tool.mcp-tools-sql]` table appended to the
   current directory's `pyproject.toml`).
2. A database config at `~/.mcp-tools-sql/config.toml` pre-filled for
   the chosen backend (skipped if that file already exists, with a
   message; the existing file is **never** overwritten).

Flags:

- `--backend {sqlite|mssql|postgresql}` (required) — selects the
  starter database config block written to
  `~/.mcp-tools-sql/config.toml`.
- `--output PATH` — destination for the standalone project query
  config. Default `./mcp-tools-sql.toml`. Ignored when `--pyproject`
  is set.
- `--pyproject` — append `[tool.mcp-tools-sql]` to `./pyproject.toml`
  in the current directory instead of writing a standalone file.
  Refuses if `pyproject.toml` is missing or already contains
  `[tool.mcp-tools-sql]`.

Behaviour highlights:

- Refuses to overwrite an existing `--output` target (exit code 1).
- Refuses if `--pyproject` is requested but `pyproject.toml` is
  missing or already has `[tool.mcp-tools-sql]` (exit code 1).
- Leaves an existing `~/.mcp-tools-sql/config.toml` untouched and
  prints a notice; never silently overwrites credentials.

#### Example — sqlite

```text
$ mcp-tools-sql init --backend sqlite
Wrote mcp-tools-sql.toml
Wrote /home/alice/.mcp-tools-sql/config.toml
```

The generated `~/.mcp-tools-sql/config.toml`:

```toml
[connections.default]
backend = "sqlite"
path = "./mydb.db"
```

#### Example — mssql

```text
$ mcp-tools-sql init --backend mssql --output mcp-tools-sql.toml
Wrote mcp-tools-sql.toml
Wrote /home/alice/.mcp-tools-sql/config.toml
```

The generated `~/.mcp-tools-sql/config.toml`:

```toml
[connections.default]
backend = "mssql"
host = ""
# port = 1433                 # set only for a non-default fixed TCP port
databases = ["sales", "hr"]   # catalogs this connection routes to
default_database = "sales"    # used when the caller omits `database`
# database = "sales"          # legacy single-database form still works
username = ""
password = "${MSSQL_PASSWORD}"
driver = "ODBC Driver 18 for SQL Server"
```

One connection can reach several catalogs; see
[Multiple connections and databases](configuration.md#multiple-connections-and-databases).

#### Example — postgresql

> PostgreSQL has no backend implementation yet: `init` scaffolds the config
> and it validates, but server and `tool` startup fail with
> `Unsupported backend` once a configured query or update targets it
> (backends are created during tool registration).

```text
$ mcp-tools-sql init --backend postgresql --pyproject
Appended [tool.mcp-tools-sql] to pyproject.toml
Wrote /home/alice/.mcp-tools-sql/config.toml
```

The generated `~/.mcp-tools-sql/config.toml`:

```toml
[connections.default]
backend = "postgresql"
host = ""
port = 5432
databases = ["mydb"]          # postgresql: exactly one database per connection
username = ""
password = "${POSTGRES_PASSWORD}"
# database = "mydb"           # legacy single-database form still works
```

PostgreSQL routes to exactly one database per connection; add further
databases as additional `[connections.*]` blocks with their own credentials.

### `help config` — the config file guide

```text
mcp-tools-sql help config
```

Prints a self-contained guide to both config files: where they are found,
every key, an example of each, the setup commands in order, and how to wire
the server into an MCP client. It is meant to be enough for an LLM driving the
CLI to configure the server without these docs. A test keeps it in step with
the config models.

### `verify` — validate setup without starting the server

```text
mcp-tools-sql [--config PATH] [--database-config PATH] verify
```

`verify` runs a series of checks and prints the result section by
section. It accepts no subcommand-level flags — supply `--config` and
`--database-config` on the top-level `mcp-tools-sql` command.

Sections, in order:

| Section | Purpose |
|---------|---------|
| `ENVIRONMENT` | Python version, virtualenv status, installed package versions of `mcp_tools_sql` and `mcp_coder_utils`. |
| `CONFIG` | Project query config and database config: resolved path, parse status, sensitive-key warning when credentials are detected in the project query config. |
| `DEPENDENCIES` | Backend-conditional checks (e.g. `pyodbc` and an ODBC driver for `mssql`, `psycopg` for `postgresql`, none for `sqlite`). |
| `BUILTIN` | Built-in default queries load successfully and have at least one tool registered. |
| `CONNECTION` | Backend-shape checks (host/port/database/path/credentials), then `SELECT 1` against the configured database. A sqlite `path` of `:memory:` reports `[WARN]`: every fresh connection to `:memory:` is a new, empty database, so read paths silently return zero rows while `updates.*` still writes to the persistent connection. On Linux only, when the connection uses `backend = "mssql"` with `trusted_connection = true`, an extra `kerberos_ticket` row runs `klist -s` and reports `[ERR]` when no cached Kerberos ticket is found. |
| `INSTALL INSTRUCTIONS` | Aggregated install hints from any failing `[ERR]` rows above (printed only when at least one row carries a hint). |
| `QUERIES` | Per-configured-query: SQL `EXPLAIN`, a read-only proof, well-formed parameters, `max_rows_default > 0`, `max_rows_hard > 0`. The read-only check runs once per declared backend variant (`<name>.read_only[<backend>]`), not just the pinned one, so a write hiding in a `[queries.<name>.backends.<other>]` override is caught before the config ships. A `backends.<key>` that maps to no backend (e.g. `postgresql`, or a typo) is dead config and yields a `[WARN]` row rather than an error. A query whose pinned SQL fails the read-only proof is never `EXPLAIN`ed — its `<name>.sql` row reads `(skipped)`, because sending the database SQL the server will refuse only reports the wrong reason. Skipped when `CONNECTION` failed. |
| `UPDATES` | Per-configured-update: table exists, key column exists, all field columns exist. Skipped when `CONNECTION` failed. |

Each row is one of three statuses:

- `[OK]`  — check passed.
- `[WARN]` — non-fatal issue; counted separately and never part of the
  exit code. The cases are: sensitive keys (e.g. `password`) in the
  project query config, which still run but should be moved to
  `~/.mcp-tools-sql/config.toml`; a check skipped because its connection
  is unreachable (that connection's own probe reports the `[ERR]`); a
  sqlite `path` of `:memory:`; a `backends.<key>` on a configured
  query that maps to no backend; and a `<name>.sql` row skipped because
  the query is not read-only (that query's own read-only row reports the
  `[ERR]`).
- `[ERR]` — check failed; the trailing summary line will include
  this in its error count and `verify` will exit with code 1.

When `CONNECTION` fails, the `QUERIES` and `UPDATES` sections are
skipped and a one-line skip summary is emitted before the trailing
total, e.g.:

```text
connection failed; skipped 3 query checks, 1 update checks
```

#### Example — SQLite happy path

```text
$ mcp-tools-sql verify
=== ENVIRONMENT ===
[OK]  python_version                3.11.9
[OK]  virtualenv                    /home/alice/projects/demo/.venv
[OK]  mcp_tools_sql                 0.1.0
[OK]  mcp_coder_utils               0.1.4

=== CONFIG ===
[OK]  query_config_path             /home/alice/projects/demo/mcp-tools-sql.toml
[OK]  query_config_parse            loaded
[OK]  database_config_path          /home/alice/.mcp-tools-sql/config.toml
[OK]  database_config_parse         loaded

=== DEPENDENCIES ===
[OK]  info                          (no optional dependencies for sqlite)

=== BUILTIN ===
[OK]  default_queries_loaded        5 queries
[OK]  tools_registered_count        5 tools

=== CONNECTION ===
[OK]  backend                       sqlite
[OK]  path                          ./mydb.db
[OK]  credentials                   (not required for sqlite)
[OK]  select_1                      ok

=== QUERIES ===
[OK]  get_user.sql                  EXPLAIN ok
[OK]  get_user.read_only[sqlite]    read-only
[OK]  get_user.params               well-formed
[OK]  get_user.max_rows_default     100
[OK]  get_user.max_rows_hard        100
... (one [OK] row per configured query) ...

=== UPDATES ===
... (skipped when no updates are configured) ...

12 checks passed, 0 warnings, 0 errors
```

#### Example — failure with install hint

```text
$ mcp-tools-sql verify
=== DEPENDENCIES ===
[ERR]  pyodbc                       (not installed)  - No module named 'pyodbc'
...
=== INSTALL INSTRUCTIONS ===
[OK]  hint_0                        pip install mcp-tools-sql[mssql]

5 checks passed, 0 warnings, 1 errors
```

### `tool` — list and call MCP tools directly

```text
mcp-tools-sql tool
mcp-tools-sql tool --help
mcp-tools-sql tool <name> --help
mcp-tools-sql tool <name> [--flag value ...]
```

Lists, describes, and invokes every tool the current config would register
with the MCP server — schema introspection, `query_*`, `update_*`,
`validate_sql`, `count_records`, `summarize_columns`, `read_databases` —
without an MCP client or LLM. Supply `--config` and `--database-config` on
the top-level `mcp-tools-sql` command, as with `verify`.

The tool list depends on the config, so even `tool --help` needs configs that
load. Without them `tool` exits 1 and points at `mcp-tools-sql help config`.

Bare `tool` and `tool --help` are the same code path: both print the full
tool listing (one `name  description` line per tool, sorted by name)
followed by the exit codes table below, and both exit 0 — there is no
separate `--list` flag.

`tool <name> --help` prints that tool's docstring plus one block per
parameter (required/optional, type, choices, default, description), read
from the tool's own JSON schema — the same detail pydantic validates
against. An unrecognized tool name exits 2 with a usage hint on stderr,
like any other argparse error.

#### Flags

One scalar `--<param>` flag is generated per parameter of the tool's Python
signature, required when the parameter has no default. Two parameter names
get a repeatable flag instead of a scalar one:

| Flag | Tools | Behaviour |
|------|-------|-----------|
| `--param KEY=VALUE` | `validate_sql`, `count_records`, `summarize_columns` | Repeatable. Binds `KEY` to the SQL placeholder `:KEY`. Values are passed through as plain strings — no JSON parsing, no type inference. |
| `--column NAME` | `summarize_columns` | Repeatable. One `--column` per column to profile. |

For `update_*` tools, an omitted optional-field flag leaves that column
unchanged. Every `update_*` flag is a plain scalar, so there is no way from
this CLI to pass an explicit `None` for an optional field — passing the flag
always sets a value, and only omitting it leaves the column untouched.

#### Exit codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Config/connection error (bad config, can't reach DB — including a connection failure discovered lazily mid-call) |
| 2 | Argparse parse error (unknown flag, unknown tool name, missing required flag) |
| 3 | Tool rejected the call (pydantic `Field` validation, or a body-level `KeyError`/`TypeError`/`ValueError`) |
| 4 | Backend/SQL execution error (query ran, database returned an error) |

`validate_sql`, `count_records`, `summarize_columns` never raise — these
three always exit 0 and print their returned text as-is.

#### Example — schema introspection

```text
$ mcp-tools-sql tool read_tables --schema main
... table listing ...
```

#### Example — configured update

```text
$ mcp-tools-sql tool update_set_name --id 1 --name Alice
Updated 1 row in customers where id=1.
```

#### Example — `validate_sql` with bind params

```text
$ mcp-tools-sql tool validate_sql --sql "SELECT 1 WHERE :id = :id" --param id=5
Valid.
```

### `help` and `--version`

- `mcp-tools-sql help` is equivalent to `mcp-tools-sql --help`: it
  prints the top-level help and exits 0. The top-level help ends with the
  getting-started commands in order. `mcp-tools-sql help config` prints the
  config guide (see above).
- `mcp-tools-sql --help` and `mcp-tools-sql -h` print the top-level
  help; `mcp-tools-sql <command> -h` prints help for that subcommand.
- `mcp-tools-sql --version` prints `mcp-tools-sql <version>` and
  exits 0.

## Exit codes

| Code | Meaning |
|------|---------|
| `0`  | Success. For `verify`, no `[ERR]` rows were emitted. |
| `1`  | User-recoverable error in `init`, `verify` or `tool`: missing/invalid config, refused overwrite, failed connection, or any `[ERR]` row in `verify`. |
| `2`  | Argparse parse error (unknown flag, missing required value, etc.). The CLI also prints `Try 'mcp-tools-sql --help' for more information.` to stderr in this case. The server (no command) also exits `2` when its config fails to load, after logging the reason and pointing at `verify`. |
| `3`, `4` | `tool` only — the tool rejected the call, or the database returned an error. See [`tool` exit codes](#exit-codes). |
| `130` | The server was interrupted (Ctrl+C). |
