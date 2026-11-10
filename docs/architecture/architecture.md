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
- **Bounded cost**: Statement and login timeouts per connection; `[limits]`
  caps output chars, cell chars and counted rows
- **Multi-backend**: SQLite and MS SQL Server behind a common abstraction
  (PostgreSQL config is accepted; the backend is not implemented yet)

### Design Principles

- **The config is the security boundary.** Every statement whose rows reach the
  LLM is declared up front. Updates are structured (table + key + fields); the
  server generates the SQL.
- **Bounded output.** Every result is truncated with a clear message ("showing
  100 of 4,832 rows") so a single call cannot flood the context window.
- **Design for the hard cases.** The driving use cases are:
  - *Wide-table discovery* — find the right schema, table and a handful of
    columns among 1,000+ in a customer data warehouse, then pull the data.
    Each tool call informs the next.
  - *Master data mapping* — look an entity up in several systems with
    configured queries, confirm candidates with the user, write the mapping
    with an update tool; later run the same tools in batch via automated
    prompting.

  If those work, simpler scenarios do too.

### Out of Scope (Decided)

- **Ad-hoc query execution.** There is no `run_select` / `run_update`. Result
  rows come only from configured queries. `validate_sql`, `count_records` and
  `summarize_columns` accept read-only SQL but return plans, counts and
  column profiles, not result sets.
- **Numeric analysis in SQL.** Heavy computation belongs in downstream scripts
  (Python/pandas); this server does exploration and retrieval.

### Stakeholders

- **LLM clients**: Claude Code, Claude Desktop, VSCode, mcp-coder — primary consumers
- **Data analysts**: Configure queries and deploy the server

---

## 2. Architecture Constraints

- Python 3.11+
- MCP protocol via STDIO transport (FastMCP)
- Pydantic for all models (config, dynamic tool params, internal)
- Two runtime config files: `~/.mcp-tools-sql/config.toml` (connections) and
  `mcp-tools-sql.toml` (queries; alternatively `[tool.mcp-tools-sql]` in the
  user project's `pyproject.toml`). See [configuration.md](../configuration.md).

---

## 3. Context & Scope

```
┌─────────────────┐    STDIO/MCP     ┌──────────────────┐    DB driver   ┌─────────────┐
│   MCP Client    │◄────────────────►│  mcp-tools-sql   │───────────────►│  Database   │
│                 │                  │                  │                │             │
│ • Claude Code   │                  │  Built-in tools: │                │ • SQLite    │
│ • Claude Desktop│                  │   schema intro.  │                │ • SQL Server│
│ • VSCode        │                  │  Configured tools│                │             │
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
│  Toolset Layer                                      │
│  └── mcp_tools_sql.toolset                          │
├─────────────────────────────────────────────────────┤
│  Verification Layer                                 │
│  └── mcp_tools_sql.verification (subpackage)        │
├─────────────────────────────────────────────────────┤
│  Tool Layer                                         │
│  ├── mcp_tools_sql.schema_tools                     │
│  ├── mcp_tools_sql.query_tools                      │
│  ├── mcp_tools_sql.update_tools                     │
│  ├── mcp_tools_sql.validation_tools                 │
│  ├── mcp_tools_sql.count_tools                      │
│  └── mcp_tools_sql.summarize                        │
├─────────────────────────────────────────────────────┤
│  Infrastructure Layer                               │
│  ├── mcp_tools_sql.backends (sqlite, mssql)         │
│  └── mcp_tools_sql.formatting                       │
├─────────────────────────────────────────────────────┤
│  Config / SQL Layer                                 │
│  ├── mcp_tools_sql.config (models, loader)          │
│  └── mcp_tools_sql.sql_ast (sqlglot owner)          │
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

The `tool` subcommand (`cli/commands/tool.py`) adds a new `cli.commands →
server` edge: it calls `build_tool_server()`, which builds the toolset
eagerly and returns a fully registered `ToolServer`, exactly as `run_server`
does. The CLI lists and calls `server.toolset.specs`, validating arguments
through each spec's `args_model` — so its tool list matches the MCP
server's, and `close()` releases backend connections in both paths.
Because the legal tool names (and each tool's own flags) aren't known until
config loads, argument parsing is two-phase: `main.py`'s top-level parser
uses `parse_known_args` and leaves everything after the `tool` token
unparsed, and `tool.py` then builds a per-tool `argparse.ArgumentParser` at
runtime from the signature of that spec's `fn`.

### Verification Layer (`mcp_tools_sql.verification`)

The verification engine was extracted from `cli/commands/verify.py` in
issue #21 to keep the CLI module under the 600-line file-size limit and
to make the engine reusable from non-CLI consumers: the server's `verify`
MCP tool and Python callers (`docs/python-api.md`). The orchestrator
`verify_all(config_path, db_config_path, project_dir=None)` loads both
configs once, entry by entry (`verify_config_files`), composes every
section in a canonical order and returns a `VerifyResult` dict: an ordered
list of `VerifySection`s (`title`, `ok`, `checks` keyed by row label, each
a `CheckResult` with `ok`/`value`/`severity`), `skipped_queries` /
`skipped_updates` counts, set only when a failed connection skipped
QUERIES/UPDATES, and a `summary` block (`connections` reachability per
connection, valid `query_count` / `update_count`, `allow_updates`); the
CLI shim is a pure printer that iterates `sections` as-is. The subpackage sits
at the `tool_implementation` layer (same as `schema_tools`/`query_tools`)
in `tach.toml`, and on its own line in `.importlinter` (above
`schema_tools|...`) because it imports from `schema_tools.load_default_queries`
and `query_helpers.extract_sql_params`.

`toolset` depends on `verification` (and `tool_logging`) for the `verify`
tool. The tool calls `verify_all` on the config paths the toolset was
built from, so it re-reads both files from disk with its own
`BackendRegistry` and never touches the toolset's registry, then returns
`verification.render.render_short` output plus a note that the running
tools keep the config they were built with.

### Toolset (`mcp_tools_sql.toolset`)

One factory builds every tool as a framework-neutral `ToolSpec`
(`mcp_tools_sql.utils.tool_spec`), so the MCP server, the CLI `tool`
subcommand and agent-workbench get the same names, descriptions, validation
and groups.

- `build_toolset(query_config, database_config=None) -> SqlToolset` loads
  both config files and delegates to `assemble_toolset`, which builds from
  already-loaded objects (config, targets, `BackendRegistry`,
  `allow_updates`) and owns the registry from then on — it closes it if
  the build fails.
- `SqlToolset` exposes `.specs`, `.targets`, `.query_config` and
  `.close()` (closes the registry); it is also a context manager.
- Rebuild = call `build_toolset` again, swap the new toolset in and close
  the old one. There is no rebuild method.
- Nothing in the toolset or the toolkits imports `mcp`
  (`no_mcp_on_export_path` contract); `server.FastMCPSink` adapts the specs
  to FastMCP.

| Group | Tools | read_only |
|---|---|---|
| `sql.schema` | tools from `default_queries.toml`, `read_databases` | True |
| `sql.validation` | `validate_sql`, `verify` | True |
| `sql.profiling` | `count_records`, `summarize_columns` | True |
| `sql.query` | `query_*` | True |
| `sql.update` | `update_*` | False |

### Key Modules

| Module | Responsibility |
|--------|---------------|
| `main.py` | CLI: argparse, per-command logging setup (level + file resolution), subcommands (server/init/verify) |
| `server.py` | Registers the toolset's specs into FastMCP, starts STDIO transport |
| `toolset.py` | `build_toolset` / `assemble_toolset`: every tool as a `ToolSpec` in one `SqlToolset`; builds the `verify` and `read_databases` tools |
| `schema_tools.py` | Built-in introspection: schemas, tables, columns, relations |
| `query_tools.py` | Dynamic registration of configured SELECT tools. Each query's resolved SQL must pass a read-only AST gate at registration; a violating query is skipped with a logged warning and the rest register normally |
| `update_tools.py` | Dynamic registration of configured UPDATE tools |
| `validation_tools.py` | SQL validation via EXPLAIN |
| `summarize/` | `summarize_columns` column profiling. `source.py` resolves the profiling **source** into one `Source` value object — either a persisted table (`schema`+`table`, types from the catalog) or an arbitrary read-only SELECT (`sql`, wrapped as a `(...) AS src` derived table; types come from `sys.dm_exec_describe_first_result_set` on T-SQL, falling back — with a footer note — to the few-row value probe that SQLite always uses). `render.py` builds the deep and triage text views, `tools.py` registers the tool and orchestrates the pipeline. Downstream of `Source` nothing branches on which path produced it. The package imports no sqlglot: SQL work goes through `sql_ast`. |
| `config/models.py` | Pydantic models for all config |
| `config/loader.py` | TOML loading, validation, connection resolution |
| `sql_ast/placeholders.py` | The only sqlglot-backed SQL analysis for the tools: `:name` placeholder extraction and translation, statement counting/kind, leading-CTE check, `basic_preflight`. Every parsing function raises `SqlParseError` instead of sqlglot errors |
| `sql_ast/summarize_queries.py` | `summarize_columns` SQL: type categoriser, `where` gate, count / scalar-aggregate / value-list SQL built as sqlglot ASTs; opaque `SourceRef` / `Predicate` handles |
| `sql_ast/source_queries.py` | Parsing and rendering behind the `summarize_columns` `sql=` source path; callers see only a `SourceRef` and SQL strings |
| `backends/base.py` | `DatabaseBackend` ABC + factory. Read-only execution comes in two shapes: `execute_readonly_query` (dict rows, the default) and `execute_readonly_query_with_columns` (ordered column names + raw row tuples, under the same read-only guarantee). The second exists because dict rows discard `cursor.description` and silently collapse duplicate column names — which the `summarize_columns` value probe must be able to detect and reject. `iter_readonly_batches` yields read-only rows in `fetchmany` batches for the query/schema tool path. `QueryTimeoutError` is the one statement-timeout exception; `translate_timeout` maps driver errors (SQLite interrupt, SQLSTATE `HYT00`) to it. Every other driver error leaves the backend as the neutral `BackendError` (`BackendConnectionError` for connection-shaped errors), same `str()`, driver exception chained — callers never catch driver types. `explain(sql, params, isolated=False)`: `isolated=True` runs on a fresh single-use connection where the backend has one (MSSQL SHOWPLAN). |
| `backends/sqlite.py` | SQLite implementation |
| `backends/mssql.py` | SQL Server implementation (pyodbc, imported lazily); `pyodbc_version` / `odbc_drivers` dependency probes |
| `backends/postgresql.py` | `psycopg_version` dependency probe (no backend yet) |
| `result_limits.py` | `collect`: the single collection path for query/schema tools (one source per database). Applies the `*_filter` glob per batch, admits display rows under `max_rows` and the output-char budget, cuts long cells, counts matched rows up to `max_count_rows` / the counting time limit, and catches statement timeouts inside the batch loop |
| `formatting.py` | Result → LLM-friendly text (tabular, truncated). `render_limited` builds the `[Output truncated: ...]` message, fan-out footer, cell-cut line and per-database error lines |
| `tool_logging.py` | Per-tool-call logging context manager (INFO counts, DEBUG params, ERROR duration) |
| `verification/` | Verifier engine: environment, config, dependencies, builtin, connection, queries, updates. Orchestrated by `verify_all`. Consumed by the `verify` CLI subcommand and the toolset's `verify` tool. |

---

## 5. Dynamic Tool Registration

Configured queries/updates become MCP tools at server startup via `mcp.add_tool()`. Parameter schemas are generated at runtime using Pydantic `create_model()`.

Tool naming convention:
- `query_<name>` — configured SELECT tools
- `update_<name>` — configured UPDATE tools
- No prefix — built-in tools (read_schemas, read_tables, etc.)

### Multi-connection / multi-database routing (two-axis model)

Routing has two independent axes: a **connection** (server + backend +
credentials) and, within it, a **database** (catalog). The unit of execution is
a `(connection, database)` **target**, built by copying the connection config
with `database` set to the chosen catalog — so the four `INFORMATION_SCHEMA`
builtins and any configured SQL run verbatim against the right catalog with no
SQL rewriting. `config` resolves the config-order list of targets
(`resolve_targets` → `ResolvedTargets`); `backends/registry.py` lazily
instantiates and caches one backend per target and owns `close_all()` (kept in
`backends` to respect the `config`-may-not-import-`backends` contract). The
server builds both and closes the registry in a `finally`.

The tool surface is **conditional** and byte-identical for single-target
installs:

- A `connection` parameter is added to the read-only schema builtins only when
  more than one connection is configured; a `database` parameter and the
  config-only `read_databases` tool are added only when more than one target
  exists. Both parameters are keyword-only with a runtime-built `Literal` enum
  of the legal names.
- `database = "*"` fans out a schema builtin across every database of the
  selected connection. Each database is one `result_limits.Source`, read in
  config order in batches by the same `collect` call the single-target path
  uses, so the display budget (`max_rows`, output chars) and the counting
  budget (`max_count_rows`, counting time limit) are shared across databases.
  Merged rows carry a `_database` source column. On truncation a
  `Matched: ...` footer gives per-database counts — `N+` where counting
  stopped early, `not queried (limit reached)` or `not queried (stopped:
  statement timeout)` for databases after the stop — and a failing database
  gets its own error line while the others are still read. There is no
  `connection = "*"`.
- `read_databases` is named for its result (the list of routable databases),
  matching the `read_*` builtin family; it reads config only and touches no
  database.
- `[queries.*]` / `[updates.*]` may pin `connection` / `database`, so
  `query_*` / `update_*` bind their target at registration and take no runtime
  routing params. `validate_sql` / `count_records` resolve backend and dialect
  per call from a runtime `database` param.

**Security note (decision 26).** The `databases` list is a routing/discovery
list, **not** an authorization boundary. A connection still reaches any catalog
its login can see (three-part `db.schema.table` names work verbatim), so
least-privilege must be enforced with per-connection database credentials at the
server — not by editing `databases`.

---

## 6. Cross-cutting Concerns

### Logging
- stdlib `logging` with structlog JSON backend (via mcp-coder-utils)
- `@log_function_call` decorator for timing and parameter capture
- **Two sinks with independent thresholds**: a JSON file at the resolved
  `--log-level`, plus a plain-text stderr console at `OUTPUT`
- **Per-command defaults**: `server` → `INFO` + a per-launch file under
  `~/.mcp-tools-sql/logs/`; `init`/`verify` → `OUTPUT`, console only.
  Resolved by the pure helpers `_resolve_log_level` / `_resolve_log_file` in
  `main.py`
- `--console-only` suppresses the file and takes precedence over `--log-file`
- Server startup failures go through `logger.error` (always recorded) plus an
  `OUTPUT`-level hint, following `mcp_coder`'s CLI convention
- Paths under the user home come from `utils/user_app_data.py`

### Architecture Enforcement
- `tach.toml` — module boundary enforcement
- `.importlinter` — import contract validation, including library isolation:
  `sqlglot` only in `sql_ast`; `pyodbc`, `psycopg` and `sqlite3` only in
  `backends` (tests: owner-mirroring `tests/sql_ast`, `tests/backends`, plus
  `tests/sqlite_fixtures.py` for `sqlite3`)

### Security
- Credentials in user config (`~/`), never in project repo
- Parameterized queries only — no string interpolation
- UPDATE requires unique key — prevents mass updates
- Row limits on all results — prevents context overflow
- `[limits]` bounds every query/schema result: `max_output_chars` (rendered
  table size), `max_cell_chars` (long values are cut) and `max_count_rows`
  (rows counted past the display set). Reads are batched, so memory stays at
  about the display rows plus one batch
- Statement timeout (`query_timeout_seconds`, all backends) and login timeout
  (`connect_timeout_seconds`, SQL Server) — no query runs forever
- Configured queries are proved read-only by AST inspection before registration
  and then execute through the backend's read-only path — unconditionally;
  `allow_updates` governs `updates.*` only. The DB-level backstop differs per
  backend: on SQLite `execute_readonly_query` opens a `PRAGMA query_only = ON`
  connection, while on MSSQL it delegates to `execute_query`, so there the
  backstop is the operator's `db_datareader` + `db_denydatawriter` login and the
  AST gate is the whole in-process enforcement
