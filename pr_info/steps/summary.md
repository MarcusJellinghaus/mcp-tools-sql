# Summary — Query Validation Tool (`validate_sql`)

Implements issue #8. Adds an MCP tool that validates a SQL string via the database's EXPLAIN mechanism without executing it. Safe for SELECT, UPDATE, INSERT, DELETE, and DDL on both SQLite and MSSQL backends.

## Goal

Expose `validate_sql(sql, *, params=None, return_plan=False) -> str` as an MCP tool. Returns `"Valid."` or a labelled error verdict (`"Invalid SQL. ..."`, `"Invalid parameters. ..."`, `"Database connection error. ..."`, `"Unexpected error. ..."`). Optional `return_plan=True` appends the execution-plan text on success only.

## Architectural / design changes

### New context-manager primitive on `DatabaseBackend`

Add `get_isolated_connection() -> AbstractContextManager[Any]` to the backend abstract base. Purpose: yield a single-use connection.

- **SQLite** — yields the persistent connection unchanged. `EXPLAIN QUERY PLAN` never executes the statement, so isolation is a no-op.
- **MSSQL** — builds a fresh `pyodbc` connection from `_build_connection_string(self._config)`, yields it, closes it on context exit (including on exception). Defence-in-depth: any session-control statement that slipped past pre-flight is contained to a connection that is closed immediately after.

This is the smallest primitive that keeps validation policy out of the backend interface. Adding `explain_isolated()` was rejected to avoid `*_isolated()` method proliferation as future features need isolation.

### `validation_tools.py` replaces its stub

- Module-level defensive `pyodbc` import builds `_PYODBC_ERROR` tuple for the exception ladder (works on the SQLite-only install path).
- `async def validate_sql(...)` is registered with a fixed signature via `mcp.add_tool(fn, name="validate_sql", description=...)`. The dynamic `build_tool_fn` machinery used by `QueryTools` / `UpdateTools` / `SchemaTools` is not needed.
- Each parameter wrapped as `Annotated[type, Field(description=...)]` so MCP clients see per-param help text.
- Pre-flight (no DB round-trip): empty/whitespace, multi-statement (`sqlparse.parse`), session-control first keyword (`USE` / `SET` / `DECLARE`), and missing param names. Uniform error-prefix shape so the LLM sees one output format.
- 5-bucket exception classification ladder, specific-first, with `Exception` as final catch-all. Never re-raised to the LLM.
- MSSQL EXPLAIN runs on the isolated connection (SHOWPLAN dance in `validation_tools.py`, mirroring the `finally`-pattern in `MSSQLBackend.explain()`). SQLite calls `backend.explain(sql, params)` directly.
- `ValidationTools.__init__` takes `backend` + `backend_name` (small deviation from the issue's one-arg sketch) so the tool body dispatches SQLite vs MSSQL path via `backend_name`. Matches the constructor pattern of `QueryTools` / `UpdateTools` / `SchemaTools`.
- Logging via `log_tool_call("validate_sql", params or {}, sql=sql)`; `rec.record(rows=0, cols=0)`.

### Server wiring

`ToolServer._register_builtin_tools` registers `ValidationTools(self._backend, self._backend_name).register(self._mcp)` after `SchemaTools`. `schema_tools.py` gains a module-scope `_PROGRAMMATIC_BUILTIN_TOOLS = ("validate_sql",)` tuple (defined alongside `load_default_queries()` to keep the `server` → `schema_tools` dependency one-way and avoid any circular import); `server.py` imports the tuple from there. `run_server` adds `len(_PROGRAMMATIC_BUILTIN_TOOLS)` to the `builtin_tools=<N>` startup log counter, which currently derives only from `len(load_default_queries())`. `load_default_queries()` gains an optional `path: Path | None = None` parameter (defaulting to the current hard-coded location) so tests can inject a temporary TOML file, and is taught to skip (with a warning log) any TOML entry whose name collides with a programmatic builtin — names in the tuple are reserved.

### `validate_sql` is registered regardless of `allow_updates`

EXPLAIN never executes the statement on either backend, so validating UPDATE/INSERT/DELETE/DDL is safe even when writes are disabled. Gating would prevent users from sanity-checking update queries before flipping `allow_updates` on.

## Folders / modules / files created or modified

**Modified:**
- `src/mcp_tools_sql/backends/base.py` — add abstract `get_isolated_connection()` method.
- `src/mcp_tools_sql/backends/sqlite.py` — implement no-op `get_isolated_connection()`.
- `src/mcp_tools_sql/backends/mssql.py` — implement fresh-connection `get_isolated_connection()`.
- `src/mcp_tools_sql/validation_tools.py` — replace stub with full implementation.
- `src/mcp_tools_sql/server.py` — wire `ValidationTools`, import `_PROGRAMMATIC_BUILTIN_TOOLS` from `schema_tools`, bump `builtin_tools` counter.
- `src/mcp_tools_sql/schema_tools.py` — define `_PROGRAMMATIC_BUILTIN_TOOLS` tuple, give `load_default_queries()` an optional `path: Path | None = None` parameter for test injection, and skip-with-warning for TOML entries colliding with a programmatic builtin.
- `tests/backends/test_sqlite.py` — tests for SQLite isolation primitive.
- `tests/backends/test_mssql.py` — tests for MSSQL isolation primitive (unit + integration).
- `tests/test_server.py` — assert `validate_sql` is among registered tools.
- `tests/test_default_queries.py` — assert TOML collision skip emits a warning and does not register the colliding name.

**Created:**
- `tests/test_validation_tools.py` — pre-flight, param handling, success, failure, integration (SQLite + MSSQL).

**Untouched:** the dynamic `build_tool_fn` machinery, `query_tools.py`, `update_tools.py`, `schema_tools.py`, `default_queries.toml`. No new dependencies; `sqlparse` is already a project dependency.

## Step ordering

1. **Step 1** — Backend isolation primitive (foundation).
2. **Step 2** — `validate_sql` implementation + unit tests + SQLite integration (depends on Step 1's primitive).
3. **Step 3a** — Wire `validate_sql` into `ToolServer` + programmatic-builtin tuple + TOML collision skip + server-registration unit test (depends on Step 2).
4. **Step 3b** — MSSQL integration tests for `validate_sql` (depends on Step 3a).

Each step ends with a passing `pylint` / `pytest` / `mypy` run and produces exactly one commit.
