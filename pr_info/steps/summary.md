# Summary — `count_records` tool + `sqlparse` → `sqlglot` migration (Issue #38)

## Goal

1. Migrate the project's SQL-parsing foundation from **`sqlparse`** (non-validating
   tokenizer) to **`sqlglot`** (dialect-aware AST parser/transpiler).
2. Add a new **read-only** built-in MCP tool `count_records(sql, params)` that
   returns how many rows a `SELECT` would produce, executed as a
   `SELECT COUNT(*)` wrapper, with the **sqlglot AST as the primary security
   layer** and DB read-only access as the backstop.

## Architectural / design changes

### Parsing foundation
- **Single parser across the codebase.** `sqlglot` replaces `sqlparse`. Removed
  from `pyproject.toml` together with its mypy override; `sqlglot` added as a
  runtime dependency.
- **`utils/sql_placeholders.py` becomes the single neutral sqlglot module.** It
  keeps its filename (to avoid rename churn) but broadens in scope: placeholder
  helpers **plus** the shared analysis helpers (dialect mapping, fail-closed
  parse, statement counting, first-statement-kind, the read-only gate, and the
  COUNT-wrap builder). It stays at the `utils` layer — the only layer that
  `backends` (infrastructure) may legally depend on — so backends and tool
  modules can all import it without a sibling cross-import.
- **"Never rewrite; normalize only" is dropped.** Executed/rendered SQL is now
  sqlglot-rendered (dialect-targeted), not the user's verbatim text. This is an
  accepted, deliberate consequence of the AST migration (issue decision).
- **Fail-closed parse contract.** If sqlglot cannot parse the SQL, both
  `validate_sql` and `count_records` reject *without executing*, surfacing
  sqlglot's own message as `Invalid SQL. ParseError: <message>`.

### Security model (reversed from the original framing)
- **Layer 1 (primary) — sqlglot AST.** `count_records` positively proves the
  statement is read-only: the root must be a read-only construct and no write
  nodes (`Insert`/`Update`/`Delete`/`Merge`/`Create`/`Drop`/`Alter`/`Truncate`),
  `SELECT … INTO`, or data-modifying CTEs may appear anywhere in the tree.
- **Layer 2 (backstop) — DB-enforced read-only.** SQLite uses a fresh per-call
  connection with `PRAGMA query_only = ON`; MSSQL relies on a documented
  read-only login (`db_datareader` + `db_denydatawriter`).
- **The read-only gate is `count_records`-only.** `validate_sql` keeps its
  contract: it validates writes too (SELECT/UPDATE/INSERT/DELETE/DDL) and does
  **not** call the gate.

### Backend seam
- New `execute_readonly_query(sql, params) -> list[dict]` on the
  `DatabaseBackend` ABC (`@abstractmethod`). SQLite: fresh
  `PRAGMA query_only=ON` connection (`row_factory = sqlite3.Row`), closed after
  use. MSSQL: trivially delegates to `execute_query` (wrapper + gate +
  documented read-only login is the model — no `SET TRANSACTION`).

### `count_records` tool
- New `count_tools.py` module, a read-only sibling to `validation_tools.py` at
  the `tool_implementation` layer. Registered in
  `server._register_builtin_tools` (not gated by `allow_updates`) and added to
  `PROGRAMMATIC_BUILTIN_TOOLS`.
- AST-wrap (rendered per dialect):
  `SELECT COUNT(*) AS row_count FROM (<sql>) AS count_sub`. Reads
  `rows[0]["row_count"]`, returns the bare number string (e.g. `"42"`).
- Deterministic pre-execution rejection of MSSQL leading `WITH` (T-SQL forbids a
  CTE inside a derived table). Logs `log_tool_call("count_records", …, rows=1, cols=1)`.

### Dialect mapping
- `sqlite → "sqlite"`; `mssql` / `pyodbc → "tsql"`, via a small helper
  `to_dialect(backend_name)`.

## KISS notes (deliberate simplifications, all preserving issue requirements)
- **One shared module**, not two (broaden `sql_placeholders.py`).
- **No new whole-statement render path in `validate_sql`** — its MSSQL explain
  path runs rendered SQL automatically because `substitute_named_with_literals`
  is reimplemented on sqlglot; SQLite explain stays verbatim (it doesn't execute).
- **MSSQL `execute_readonly_query` delegates to `execute_query`** (one line).
- **Gate / preflight are small `find`/root-type AST inspections**, no visitor framework.
- **No "input normalization" step** exists today, so none is added-then-removed.

## Files created / modified

### Created
- `pr_info/steps/summary.md`, `step_1.md` … `step_5.md`
- `src/mcp_tools_sql/count_tools.py`
- `tests/test_count_tools.py`

### Modified
- `pyproject.toml` — add `sqlglot`, remove `sqlparse` + its mypy override
- `src/mcp_tools_sql/utils/sql_placeholders.py` — reimplement on sqlglot + new shared helpers
- `src/mcp_tools_sql/validation_tools.py` — preflight on sqlglot, fail-closed parse
- `src/mcp_tools_sql/backends/base.py` — `execute_readonly_query` abstractmethod
- `src/mcp_tools_sql/backends/sqlite.py` — fresh read-only connection impl
- `src/mcp_tools_sql/backends/mssql.py` — delegate impl (+ sqlglot helpers ride in)
- `src/mcp_tools_sql/server.py` — register `count_records`
- `src/mcp_tools_sql/schema_tools.py` — add `count_records` to `PROGRAMMATIC_BUILTIN_TOOLS`
- `.importlinter`, `tach.toml` — add `count_tools` to the tool layer
- `tests/test_sql_placeholders.py`, `tests/test_validation_tools.py`,
  `tests/backends/test_sqlite.py`, `tests/backends/test_mssql.py`,
  `tests/test_server.py` — adjust for sqlglot + new tool

## Step overview (one commit each, TDD)
1. **Parsing foundation** — dependency swap + reimplement placeholder helpers on sqlglot.
2. **Shared preflight helpers + `validate_sql` migration** (fail-closed parse).
3. **`execute_readonly_query` backend seam** (ABC + SQLite + MSSQL).
4. **Read-only gate + COUNT-wrap helpers** (pure functions, unit-tested).
5. **`count_records` tool** — module + registration + architecture config (e2e).

> **Spike note:** sqlglot's exact placeholder node (`exp.Placeholder` vs
> `exp.Parameter`) and whether `:name` round-trips through a `sqlite`-dialect
> render must be confirmed empirically in Step 1 (the tests are the verification)
> and in Step 5's SQLite e2e count. Adapt the helper to the observed node type.
