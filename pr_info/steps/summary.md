# Summary — #93 Isolate sqlglot and DB drivers behind owning boundaries

## Goal

One module owns each external SQL/DB library; library types and exceptions never
cross the boundary. Enforced at the end by import-linter contracts that cover
`src` and `tests`.

| Boundary | Owns | Callers see |
|---|---|---|
| `mcp_tools_sql/sql_ast/` (new package) | `sqlglot` | strings, dataclasses, opaque `SourceRef` / `Predicate`, SQL strings out; `SqlParseError` |
| `mcp_tools_sql/backends/` | `pyodbc`, `psycopg`, `sqlite3` | `DatabaseBackend`, `BackendError` / `BackendConnectionError` (in `backends/base.py`), dependency probe functions |

Everything above (`*_tools`, `query_helpers`, `summarize/`, `cli/`, `verification/`)
imports none of the four libraries.

**No behaviour change**: user-visible messages and CLI exit codes stay byte-identical.

## Architectural / design changes

1. **New package `sql_ast/`** (no internal dependencies):
   - `placeholders.py` — moved from `utils/sql_placeholders.py` (unchanged content
     apart from error translation; `ParseError`/`SqlglotError` re-exports dropped).
   - `summarize_queries.py` — moved from `summarize/sql.py` (still holds the domain
     types `ColumnMeta`, `Category`, `categorize_type`, `metadata_sql`, `clamp_n`,
     `VALUE_LIST_*`; splitting is out of scope).
   - `source_queries.py` — new, the sqlglot code extracted from `summarize/source.py`
     (`parse_source`, `build_probe_sql`, `source_batch_sql`). A separate module
     because `summarize_queries.py` (661 lines) would otherwise exceed the 750-line limit.
   - `SqlParseError` + the `translate_parse_errors` decorator live in `placeholders.py`
     next to `single_line` (no extra module, no import cycle).
2. **Opaque SQL values**: `SourceRef` and `Predicate` become frozen dataclasses
   wrapping a private sqlglot node (`_node`), exposing only `.sql(dialect=...)`
   (`SourceRef` also `is_query`). No `exp` type appears in a public signature.
3. **`SqlParseError(Exception)`**: every public `sql_ast` function that parses
   translates any `SqlglotError` (incl. sibling `TokenError`) via one decorator.
   Carries `original_class` (sqlglot class name) and `detail` (single-line text);
   `str(exc)` equals the sqlglot message.
4. **Neutral backend exceptions** in `backends/base.py`: `BackendError(Exception)`
   and subclass `BackendConnectionError` (driver `OperationalError`/`InterfaceError`),
   both with `original_class: str`, built with `*exc.args` so `str()` is identical.
   One helper `wrap_driver_error(exc, connection_types)` builds them. Each backend
   translates only its driver's exceptions, after timeout translation and password
   redaction. `QueryTimeoutError` stays outside `BackendError`.
5. **Render sites** (`count_tools`, `validation_tools`, `summarize/tools.py`,
   `cli/commands/tool_dispatch.py`) print
   `getattr(exc, "original_class", type(exc).__name__)` instead of
   `type(exc).__name__`, so messages stay identical. `tool_dispatch` maps
   `BackendConnectionError` to exit 1 (as driver `OperationalError`/`InterfaceError` today).
6. **SHOWPLAN moves into the backend**: `DatabaseBackend.explain(sql, params=None, *, isolated=False)`.
   `MSSQLBackend.explain(isolated=True)` runs SHOWPLAN on a fresh private
   `_isolated_connection()` (renamed from `get_isolated_connection`); SQLite accepts
   and ignores `isolated`. `get_isolated_connection` leaves the ABC.
   `validation_tools` always calls `backend.explain(sql, params, isolated=True)`.
7. **Dependency probes**: `backends/mssql.py` gets `pyodbc_version()` and
   `odbc_drivers()`; new `backends/postgresql.py` holds only `psycopg_version()`.
   Each imports its driver inside the function; `verification/dependencies.py`
   keeps rows, hints and driver matching.
8. **Tests mirror source**: owner tests (`tests/sql_ast/**`, `tests/backends/**`)
   may use the raw libraries. Non-owner tests use the neutral API; direct `sqlite3`
   fixture setup goes through one helper module `tests/sqlite_fixtures.py`.
9. **Contracts**: step 1 adds the layers row and the tach module (they describe the moved
   code); step 12 adds the isolation contracts. `.importlinter` gets `sqlglot_isolation`, `pyodbc_isolation`,
   `psycopg_isolation`, `sqlite3_isolation` (shape of `subprocess_isolation`), and
   the layers contract gets `mcp_tools_sql.config | mcp_tools_sql.sql_ast` as a
   shared row below `backends`. `tach.toml` gets the `sql_ast` module.

### Decisions taken in this plan

- Layers row: `mcp_tools_sql.config | mcp_tools_sql.sql_ast` (independent siblings).
- Transition: step 5 adds the neutral exceptions to the existing upper-layer catch
  tuples *alongside* the raw driver types; step 9 removes the raw types. Every step stays green.
- `parse_source` returns `ParsedSource(ref, row_limited, order_stripped)`; `ref is None`
  means the root is not `Select`/`Union`.

## Files

### Created
- `src/mcp_tools_sql/sql_ast/__init__.py`
- `src/mcp_tools_sql/sql_ast/source_queries.py`
- `src/mcp_tools_sql/backends/postgresql.py`
- `tests/sql_ast/__init__.py`
- `tests/sql_ast/test_parse_errors.py`
- `tests/sql_ast/test_source_queries.py`
- `tests/sql_ast/test_tokenizer_premises.py`
- `tests/backends/test_base_errors.py`
- `tests/backends/test_mssql_errors.py`
- `tests/backends/test_mssql_explain.py`
- `tests/backends/test_dependency_probes.py`
- `tests/sqlite_fixtures.py`
- `tests/test_sqlite_fixtures.py`

### Moved
- `src/mcp_tools_sql/utils/sql_placeholders.py` → `src/mcp_tools_sql/sql_ast/placeholders.py`
- `src/mcp_tools_sql/summarize/sql.py` → `src/mcp_tools_sql/sql_ast/summarize_queries.py`
- `tests/test_sql_placeholders.py` → `tests/sql_ast/test_placeholders.py`
- `tests/test_basic_preflight.py` → `tests/sql_ast/test_basic_preflight.py`
- `tests/summarize/test_sql.py` → `tests/sql_ast/test_summarize_queries.py`

### Modified (src)
- `src/mcp_tools_sql/backends/base.py`, `backends/mssql.py`, `backends/sqlite.py`
- `src/mcp_tools_sql/query_helpers.py`, `count_tools.py`, `validation_tools.py`
- `src/mcp_tools_sql/summarize/source.py`, `summarize/tools.py`, `summarize/render.py`
- `src/mcp_tools_sql/cli/commands/tool_dispatch.py`
- `src/mcp_tools_sql/verification/dependencies.py`

### Modified (tests)
- `tests/backends/conftest.py`, `test_mssql.py`, `test_mssql_timeout.py`,
  `test_sqlite.py`, `test_sqlite_timeout.py`, `test_batched_read.py`, `test_registry.py`
- `tests/test_query_tools_readonly.py`, `test_validation_tools.py`, `test_tool_timeouts.py`,
  `test_query_limits_tools.py`, `test_schema_tools_fanout_limits.py`,
  `test_schema_tools_multitarget.py`, `test_count_tools.py` (if it pins raw driver types)
- `tests/summarize/test_source.py`, `test_tools.py`, `test_tools_query_source.py`,
  `test_render.py`, `test_render_clamp.py`, `conftest.py`
- `tests/cli/test_tool_dispatch.py`, `test_tool.py`, `test_main_dispatch.py`, `test_verify.py`
- `tests/verification/test_dependencies.py`
- Non-owner sqlite3 users moved onto `tests/sqlite_fixtures.py`: `tests/conftest.py`,
  `test_default_queries.py`, `test_query_limits_tools.py`, `test_query_tools.py`,
  `test_schema_tools.py`, `test_server.py`, `test_server_verify_tool.py`,
  `test_toolset.py`, `test_tool_builder.py`, `test_update_tools_execution.py`,
  `cli/test_main_dispatch.py`, `cli/test_tool.py`, `cli/test_verify.py`,
  `summarize/conftest.py`, `summarize/test_source.py`, `summarize/test_tools*.py`
  (`tests/test_module_imports.py` keeps `import sqlite3` inside a subprocess script
  string — not an import of the test module, so it is not a violation)

### Modified (config / docs)
- `.importlinter`, `tach.toml`, `vulture_whitelist.py`
- `docs/architecture/architecture.md`, `docs/quality-and-security-checks.md`, `docs/cli.md` (check only)

## Steps

| # | Kind | Title |
|---|---|---|
| 1 | move | `sql_placeholders` → `sql_ast/placeholders.py` (+ tests, tach, layers row) |
| 2 | move | `summarize/sql.py` → `sql_ast/summarize_queries.py` (+ tests, readonly test split) |
| 3 | restructure | `SqlParseError` + translation decorator |
| 4 | restructure | Opaque `SourceRef`/`Predicate`; `source.py` sqlglot-free |
| 5 | restructure | Neutral backend exceptions; upper layers catch them additively |
| 6 | restructure | SQLite backend translates driver errors |
| 7 | restructure | MSSQL backend translates driver errors |
| 8 | restructure | SHOWPLAN into `MSSQLBackend.explain(isolated=True)`; drop `get_isolated_connection` |
| 9 | restructure | Upper layers drop raw driver exception types |
| 10 | restructure | Dependency probes in backends |
| 11 | restructure | `tests/sqlite_fixtures.py`; non-owner tests off sqlite3 |
| 12 | config/docs | Isolation contracts, canary, docs |

## Constraints every step honours
- Checks after each step: `run_pylint_check`, `run_pytest_check` (`-n auto`), `run_mypy_check`,
  `run_lint_imports_check`, `run_ruff_check`; `run_format_code` before committing.
- Exception bases are `Exception`, never `RuntimeError`/`ValueError`/`KeyError`/`TypeError`.
- Drivers stay optional: no module-scope `import pyodbc` / `import psycopg`; importing
  `backends.mssql` / `backends.postgresql` works without the driver installed.
- Translate only driver exceptions (`sqlite3.Error`, `pyodbc.Error`), never `Exception`.
- Backends never wrap `SqlParseError`; it passes through.
