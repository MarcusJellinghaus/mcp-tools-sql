# Summary — Support several connections and databases (Issue #44)

## Goal

Let the server route to **N connections** (different servers *and* backends) and,
within one connection, to **N databases** (catalogs). One connection and one
database are the defaults. Schema-exploration builtins can fan out across all
databases of a connection. Cross-database SQL keeps working verbatim (three-part
names) — nothing new is needed for that.

This preserves every decision in the issue. Two simplifications are applied, both
explicitly sanctioned by the issue and both **requirement-preserving**:

- **No SQL `TOP`/`LIMIT` fan-out optimisation.** Decision 22 marks it a "droppable
  performance optimisation". We implement only the correctness path:
  fetch-all → merge in config order → truncate at the end. Per-database footer
  counts are exact for free (`len()` of a fully-fetched target), the merged total
  is capped at `max_rows`, and the post-fetch-filter special-case disappears.
  Fan-out targets are *schema-introspection* result sets (bounded metadata), so
  reading them whole is fine.
- **No unified pinned/fan-out execution abstraction — one shared
  execution+format core instead.** We do **not** build the issue's list-returning
  `resolve → execute_all` abstraction (the `ExecutionTarget`/`execute_all`
  sketch). Pinned `query_*`/`update_*` keep binding their backend at registration
  time (decision 6/11 — target is pinned in TOML). `schema_tools` gets its own
  call-time body (`build_schema_body`) that resolves the target(s) at call time.
  Both `build_query_body` and `build_schema_body` delegate to a single shared
  `execute_and_format` helper (extracted in Step 9) for the common
  max_rows/filter/logging/format tail — so the shared core has one home without
  forcing the two families through one resolver. This matches the issue's own
  "low churn" estimate for `query_tools`/`update_tools`.

## Architectural / design changes

### Runtime model (decision 11)
The unit of execution becomes a **`(connection, database)` pair**, not a
connection. A target backend is `conn.model_copy(update={"database": db})`, so the
ODBC `Database=` points at the right catalog and the four builtin
`INFORMATION_SCHEMA` queries run **verbatim** — no SQL rewriting anywhere, and
`update_tools`' two-part `schema.table` needs no change.

### Two new collaborators, placed to respect the layer contract
`config` may not import `backends`, so resolution and lifecycle are split:

| Where | What | Layer |
|-------|------|-------|
| `config/models.py` | `DatabaseSpec`, `ResolvedTarget`, `ResolvedTargets` — pure data | config |
| `config/loader.py` | `resolve_targets(query_cfg, db_cfg) -> ResolvedTargets` — pure config resolution | config |
| `backends/registry.py` (new) | `BackendRegistry` — lazily `create_backend` per target, cache, `close_all()` | infrastructure |

`server` builds both and owns lifecycle (`registry.close_all()` in `finally`).
Tool families receive `ResolvedTargets` (+ the `BackendRegistry`) instead of a
single `(backend, backend_name)`.

### Config shape (decisions 3, 4, 14, 21)
`ConnectionConfig` gains `databases` / `default_database` / `description`.
A `model_validator(mode="before")` normalises three input forms into one internal
shape (`databases: list[DatabaseSpec]`, `default_database: str`):
- **list form** `databases = ["sales", "hr"]`
- **table form** `[connections.prod.databases.sales] description = "..."`
- **legacy** `database = "sales"` → `databases=[{name:"sales"}]`, `default="sales"`
- **sqlite** → normalised to `["main"]`, default `"main"` (author still uses `path`)

`QueryConfig` / `UpdateConfig` gain optional `connection` / `database` (pinned).

### Tool surface (decisions 5, 13, 16)
Conditional, byte-identical for single-target installs:
- `connection` param appears only when **>1 connection**; `database` param and the
  new `read_databases` tool appear only when **>1 target**. Both are
  **keyword-only** with a dynamically-built `Literal` enum of legal names.
- `database="*"` fan-out on the four read-only builtins only (no `connection="*"`).
  Merged results carry a `_database` source column (only under fan-out) and a
  per-database footer breakdown on truncation.
- `validate_sql` / `count_records` keep a `database` param; dialect and backend
  resolve per-call. `query_*` / `update_*` unchanged.

### Prerequisite bug fixes (land first)
1. `translate_named_to_qmark` / `substitute_named_with_literals` gain a `dialect`
   parameter applied to **both** parse and render (fixes bracket-quoted T-SQL
   corruption `[id]`→`ARRAY(id)`).
2. `build_count_query` strips the statement-level `ORDER BY` before wrapping
   (fixes T-SQL error 1033 under the count wrapper).

### verify (decisions 9, 24, 25)
Static cross-file checks in CONFIG (no DB access); CONNECTION probes **every**
`(connection, database)` pair; M2 (QUERIES/UPDATES) resolves each entry to its own
target, reporting unreachable targets as per-connection skips; non-zero exit if any
connection fails.

## Data structures (internal)

```python
class DatabaseSpec(BaseModel):        # config/models.py
    name: str
    description: str = ""

class ResolvedTarget(BaseModel, frozen=True):   # config/models.py
    connection: str
    database: str
    config: ConnectionConfig          # .database set to this catalog
    backend_name: str                 # -> to_dialect(), resolve_sql()
    is_default: bool
    connection_description: str
    database_description: str

class ResolvedTargets(BaseModel):     # config/models.py
    targets: list[ResolvedTarget]     # config order: conns × dbs
    default: ResolvedTarget
    file_default_connection: str
    # is_multi, connection_names, database_names, for_connection(),
    # resolve_pinned() as methods
```

## Files created / modified

**Created**
- `src/mcp_tools_sql/backends/registry.py`
- `tests/backends/test_registry.py`
- `pr_info/steps/summary.md` + `step_1.md` … `step_16.md`

**Modified — source**
- `src/mcp_tools_sql/utils/sql_placeholders.py` (prereqs)
- `src/mcp_tools_sql/backends/mssql.py` (dialect threading)
- `src/mcp_tools_sql/validation_tools.py` (dialect + `database` param, per-call)
- `src/mcp_tools_sql/count_tools.py` (`database` param, per-call)
- `src/mcp_tools_sql/config/models.py` (connection/query/update + Resolved* models)
- `src/mcp_tools_sql/config/loader.py` (`resolve_targets`)
- `src/mcp_tools_sql/server.py` (registry wiring, lifecycle)
- `src/mcp_tools_sql/query_tools.py`, `update_tools.py` (per-target registration)
- `src/mcp_tools_sql/query_helpers.py` (fan-out body, conditional params, footer)
- `src/mcp_tools_sql/schema_tools.py` (runtime targets, fan-out, `read_databases`)
- `src/mcp_tools_sql/formatting.py` (fan-out footer helper)
- `src/mcp_tools_sql/verification/config_files.py`, `connection.py`, `queries.py`,
  `updates.py`, `orchestrator.py`
- `src/mcp_tools_sql/cli/commands/init.py` (multi-connection template)
- `docs/architecture/architecture.md`, `docs/cli.md`, `README.md`

**Modified — tests** (mirroring src)
- `tests/test_sql_placeholders.py`, `tests/backends/test_mssql.py`
- `tests/config/test_models.py`, `tests/config/test_loader.py`
- `tests/test_server.py`, `tests/test_query_tools.py`, `tests/test_update_tools.py`
- `tests/test_schema_tools.py`, `tests/test_validation_tools.py`,
  `tests/test_count_tools.py`, `tests/test_formatting.py`
- `tests/verification/test_config_files.py`, `test_connection.py`,
  `test_queries.py`, `test_updates.py`, `test_orchestrator.py`
- `tests/cli/test_init.py`, `tests/cli/test_verify.py`

## Step map

| Step | Theme | Commit scope |
|------|-------|--------------|
| 1 | Prereq: dialect-aware placeholder translation | sql_placeholders + mssql + validation |
| 2 | Prereq: `build_count_query` strips `ORDER BY` | sql_placeholders |
| 3 | Config models: connection/query/update multi-db fields | config/models |
| 4 | Config resolution: `resolve_targets` + Resolved* models | config/loader + models |
| 5 | `BackendRegistry` | backends/registry |
| 6 | Server wiring (behaviour unchanged, single default target) | server |
| 7 | Pinned per-target backend for `query_*` / `update_*` | query_tools, update_tools |
| 8 | `read_databases` tool (config-only, when >1 target) | schema_tools + server |
| 9 | Extract shared `execute_and_format` core from `build_query_body` (pure refactor) | query_helpers |
| 10 | schema_tools: runtime single-target `connection`/`database` params | schema_tools, query_helpers |
| 11 | schema_tools: `database="*"` fan-out + `_database` + footer | schema_tools, query_helpers, formatting |
| 12 | `validate_sql` / `count_records`: `database` param, per-call dialect | validation_tools, count_tools |
| 13 | verify: static CONFIG cross-file checks | verification/config_files |
| 14 | verify: per-pair CONNECTION probing + orchestrator registry migration | verification/connection, orchestrator, loader (del `resolve_connection`) |
| 15 | verify: per-target M2 (QUERIES/UPDATES) + skip rows + snapshot | verification/queries, updates, orchestrator |
| 16 | `init` multi-connection template + docs | cli/commands/init, docs |

Each step: write tests first, implement, and leave `pylint` / `pytest` / `mypy`
green — exactly one commit.
