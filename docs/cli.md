# mcp-tools-sql CLI Reference

This document describes the `mcp-tools-sql` command-line interface
delivered by the package's console-script entry point.

## Synopsis

```text
mcp-tools-sql [--config PATH] [--database-config PATH]
              [--log-level LEVEL] [--log-file PATH] [--console-only]
              [--version] [--help]
              <command> [<args>]
```

If no `<command>` is given (or `help` is given), the CLI prints the
top-level help and exits with code 0.

## Global flags

These flags are accepted on the top-level `mcp-tools-sql` command and
apply to every subcommand. Subcommands MAY ignore flags that do not
apply to them (e.g. `init` does not consult `--config` or
`--database-config`).

| Flag | Default | Description |
|------|---------|-------------|
| `--help`, `-h` | — | Print help for `mcp-tools-sql` (or for a subcommand when used as `<command> -h`) and exit 0. |
| `--version` | — | Print the installed package version and exit 0. |
| `--config PATH` | (auto-discovered) | Path to the project query config. Discovery falls back to `mcp-tools-sql.toml` in the current directory and then `[tool.mcp-tools-sql]` in `pyproject.toml`. |
| `--database-config PATH` | `~/.mcp-tools-sql/config.toml` | Path to the database config (connections + credentials). |
| `--log-level LEVEL` | `INFO` | One of `DEBUG`, `INFO`, `WARNING`, `ERROR`. |
| `--log-file PATH` | (none) | Append logs to this file. Ignored when `--console-only` is set. |
| `--console-only` | off | Disable file logging; log to stderr only. |

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
port = 1433
database = ""
username = ""
credential_env_var = "MSSQL_PASSWORD"
driver = "ODBC Driver 18 for SQL Server"
```

#### Example — postgresql

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
database = ""
username = ""
credential_env_var = "POSTGRES_PASSWORD"
```

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
| `CONNECTION` | Backend-shape checks (host/port/database/path/credentials), then `SELECT 1` against the configured database. |
| `INSTALL INSTRUCTIONS` | Aggregated install hints from any failing `[ERR]` rows above (printed only when at least one row carries a hint). |
| `QUERIES` | Per-configured-query: SQL `EXPLAIN`, well-formed parameters, `max_rows > 0`. Skipped when `CONNECTION` failed. |
| `UPDATES` | Per-configured-update: table exists, key column exists, all field columns exist. Skipped when `CONNECTION` failed. |

Each row is one of three statuses:

- `[OK]`  — check passed.
- `[WARN]` — non-fatal issue; the most common case is detection of
  sensitive keys (e.g. `password`, `credential_env_var`) in the
  project query config, which still runs but should be moved to
  `~/.mcp-tools-sql/config.toml`.
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
[OK]  read_schemas.sql              EXPLAIN ok
[OK]  read_schemas.params           well-formed
[OK]  read_schemas.max_rows         100
... (one [OK] row per default + configured query) ...

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

### `help` and `--version`

- `mcp-tools-sql help` is equivalent to `mcp-tools-sql --help`: it
  prints the top-level help and exits 0.
- `mcp-tools-sql --help` and `mcp-tools-sql -h` print the top-level
  help; `mcp-tools-sql <command> -h` prints help for that subcommand.
- `mcp-tools-sql --version` prints `mcp-tools-sql <version>` and
  exits 0.

## Exit codes

| Code | Meaning |
|------|---------|
| `0`  | Success. For `verify`, no `[ERR]` rows were emitted. |
| `1`  | User-recoverable error: missing/invalid config, refused overwrite, failed connection, or any `[ERR]` row in `verify`. |
| `2`  | Argparse parse error (unknown flag, missing required value, etc.). The CLI also prints `Try 'mcp-tools-sql --help' for more information.` to stderr in this case. |
