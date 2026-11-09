# Summary – #97 Query limits: statement timeout, fetch/count limits, output budget

Issue: MarcusJellinghaus/mcp-tools-sql#97 (part of agent-workbench#13, step 2c).

Goal: a query can neither run forever, nor exhaust server memory, nor flood the
LLM's context window.

## Architectural / design changes

### 1. Timeouts ride on the connection config
- `ConnectionConfig` gains `query_timeout_seconds` (default 30) and
  `connect_timeout_seconds` (default 15, SQL Server only, ignored on SQLite).
  Both `int`, `Field(gt=0)`.
- Timeouts reach the backends through the existing `ResolvedTarget.config` →
  `create_backend(config)` path. No new plumbing.
- **SQLite**: one per-statement context manager `_statement_deadline(conn,
  seconds, counting=None)` sets a progress handler on entry and removes it in
  `finally`. It wraps every statement on the persistent connection and on every
  fresh read-only connection, through execute **and** fetch.
- **SQL Server**: `_open_connection` passes `timeout=connect_timeout_seconds`
  (login timeout) to `pyodbc.connect` and sets `conn.timeout =
  query_timeout_seconds` (statement timeout). That covers the persistent
  connection and `get_isolated_connection`. `HYT00` is translated only around
  execute/fetch, never around `connect()`.

### 2. One timeout exception, one translation helper (`backends/base.py`)
- `QueryTimeoutError(seconds)`: a plain `Exception`, not a driver-error subclass.
  Its `str()` is `Query aborted after N s (statement timeout).`
- `translate_timeout(exc, seconds) -> QueryTimeoutError | None` recognises
  `sqlite_errorcode == 9` (SQLITE_INTERRUPT) and SQLSTATE `HYT00`. It is used by
  both backends and by `validation_tools._explain`.
- `Deadline` is a one-field mutable holder (`at: float | None`, monotonic). The
  caller sets it once the display set is complete; the SQLite progress handler
  interrupts at `min(statement deadline, Deadline.at)`. The statement timeout is
  never extended.
- Which deadline fired is decided by the caller from the clock (counting deadline
  passed → `counting stopped`, else `stopped: statement timeout`), so the
  exception needs no `reason` attribute.
- Tool-aware callers add the hint; backends never do.

### 3. Batched read (`DatabaseBackend.iter_readonly_batches`)
- A concrete (non-abstract) generator method yielding `list[dict]` batches. The
  default chunks `execute_readonly_query` (keeps test fakes working). SQLite and
  SQL Server override it with `cursor.fetchmany(FETCH_BATCH_SIZE)` and close the
  cursor (SQLite: also its fresh read-only connection) in `finally`, so
  `generator.close()` on early stop releases everything.
- Opt-in: only the query/schema tool path uses it. `count_records` and
  `summarize_columns` keep `execute_readonly_query`.

### 4. New module `result_limits.py`: filtering, budgets, counting
- `collect(sources, …) -> LimitedResult` is the **single** collection path for
  single-target and fan-out (`database="*"`) calls: a single target is a list of
  one source. That makes the display and counting budgets shared across
  databases with no extra code.
- Applies the `*_filter` glob per batch, admits display rows under `max_rows`
  and the char budget, cuts long cells, counts matched rows up to
  `max_count_rows` / the counting time limit / end of data, and discards counted
  rows. Memory stays at about display rows plus one batch.
- Catches `QueryTimeoutError` inside the batch loop (rows read so far are kept).
- New import-linter layer between `tool_builder` and `backends | formatting`;
  new `tach.toml` module.

### 5. Rendering and LLM messages (`formatting.py`)
- `formatting.py` owns the result shape it renders (`SourceCount`,
  `LimitedResult`), the hint constants, and `render_limited(...)`.
  `result_limits` imports them; `formatting` stays free of backend imports.
- Cells are stringified once (`None` → `""`) in `result_limits` and rendered with
  `tabulate(..., disable_numparse=True)`, so the char-budget arithmetic matches
  the rendered table exactly (numeric decimal alignment would otherwise make the
  table wider than the computed budget). Intentional visible change: numbers in
  query/schema output are left-aligned.
- The per-toolkit `_TRUNCATION_HINT` constants are removed; `render_limited`
  builds every §5 variant from plain inputs (`max_rows`, `max_rows_hard`,
  `has_sql_params`, `filter_column`, `builtin`, …).
- Message format follows the issue's §5 draft: `[Output truncated: showing X of
  Y rows (reason).` + next step + `]`. Existing `Showing N of M rows`
  assertions are updated to the new wording (intentional test churn).
- `format_rows` stays unchanged for `read_databases` and other callers;
  `format_fanout_rows` is removed once fan-out moves to `render_limited`.

### 6. `[limits]` in the project config
- `LimitsConfig` (`QueryFileConfig.limits`): `max_output_chars=80000`,
  `max_cell_chars=500`, `max_count_rows=100000`.
- `max_count_rows: Field(ge=BUILTIN_MAX_ROWS_HARD)` (`= 100`, the built-ins'
  hard limit) covers both `> 0` and "≥ the built-ins' `max_rows_hard`" with no
  code. `config` cannot import `schema_tools`, so a test keeps the constant in
  sync with `default_queries.toml`.
- Configured queries: `count_rows_violation(limits, queries)` is called from a
  `QueryFileConfig` validator and from `verify` (which validates entries
  separately), and is reported in the existing `query_config_parse` row.
- `LimitsConfig` is passed explicitly: `ToolServer` → `SchemaTools` /
  `QueryTools` → `build_schema_body` / `build_query_body` →
  `execute_and_format`. Constructor parameters default to `None` →
  `LimitsConfig()`, so existing tests that build toolkits stay valid.

### 7. Tool-level timeout handling
- `count_records`, `validate_sql`, `summarize_columns`: `except
  QueryTimeoutError` before the `Invalid SQL` handlers; append
  `Use a narrower query.`
- Update tools: return `str(exc)`, no hint.
- Query/schema tools: `Use more selective parameters.` only when the resolved
  SQL has placeholders (`sql_params`); nothing otherwise.

## Decisions taken during planning
| Topic | Decision |
|---|---|
| Fan-out vs single target | One `collect` over a list of sources |
| Which deadline fired | Inferred by the caller from the clock; no exception attribute |
| SQLite deadline | Per-statement context manager, handler cleared in `finally` |
| Exception module | `backends/base.py` (no new `backends/errors.py`) |
| Built-in `max_rows_hard` check | `Field(ge=BUILTIN_MAX_ROWS_HARD)` + sync test |
| Configured-query check | `count_rows_violation`, reused by validator and `verify` |
| Stop label for `max_count_rows` and counting time | Both `(counting stopped)` |
| Non-timeout error mid-fan-out | Rows already shown stay; database gets its error line; counting continues |
| First row too wide | `[Output truncated: the first row is wider than the 80,000-char output limit; showing 0 of N rows.` + operator line `]` |

## Files

### Created
- `src/mcp_tools_sql/result_limits.py`
- `tests/config/test_limits_config.py`
- `tests/verification/test_config_files_limits.py`
- `tests/backends/test_base_timeout.py`
- `tests/backends/test_sqlite_timeout.py`
- `tests/backends/test_mssql_timeout.py`
- `tests/backends/test_batched_read.py`
- `tests/test_tool_timeouts.py`
- `tests/test_result_limits.py`
- `tests/test_formatting_limits.py`
- `tests/test_query_limits_tools.py`
- `tests/test_schema_tools_fanout_limits.py`

### Modified
- `src/mcp_tools_sql/config/models.py` – timeout fields, `LimitsConfig`,
  `BUILTIN_MAX_ROWS_HARD`, `count_rows_violation`, `QueryFileConfig.limits`
- `src/mcp_tools_sql/verification/config_files.py` – `count_rows_violation` row
- `src/mcp_tools_sql/cli/commands/help_config.py` – guide text
- `src/mcp_tools_sql/backends/base.py` – `QueryTimeoutError`, `Deadline`,
  `translate_timeout`, `FETCH_BATCH_SIZE`, `iter_readonly_batches`
- `src/mcp_tools_sql/backends/sqlite.py` – statement deadline, batched read
- `src/mcp_tools_sql/backends/mssql.py` – login/statement timeout, `HYT00`
  translation, batched read
- `src/mcp_tools_sql/count_tools.py`, `src/mcp_tools_sql/validation_tools.py`,
  `src/mcp_tools_sql/summarize/tools.py`, `src/mcp_tools_sql/update_tools.py` –
  timeout branches
- `src/mcp_tools_sql/formatting.py` – hint constants, `SourceCount`,
  `LimitedResult`, `render_limited`; remove `format_fanout_rows`
- `src/mcp_tools_sql/query_helpers.py` – `execute_and_format`,
  `build_query_body`, `build_schema_body` use `collect` + `render_limited`
- `src/mcp_tools_sql/query_tools.py`, `src/mcp_tools_sql/schema_tools.py` –
  take `limits`, drop `_TRUNCATION_HINT`
- `src/mcp_tools_sql/server.py` – pass `config.limits`
- `.importlinter`, `tach.toml` – `result_limits` layer/module
- `docs/configuration.md`, `docs/architecture/architecture.md`
- `tests/cli/test_help_config.py` – `LimitsConfig` in `_AUTHORED_MODELS`
- `tests/test_default_queries.py` – `BUILTIN_MAX_ROWS_HARD` sync test
- Existing tests asserting old hint/`Showing` wording or calling
  `build_query_body(..., truncation_hint)` / `format_fanout_rows`:
  `tests/test_formatting.py`, `tests/test_query_helpers.py`,
  `tests/test_query_tools.py`, `tests/test_schema_tools.py`,
  `tests/test_schema_tools_multitarget.py`

## Steps
1. Config: timeouts, `[limits]`, validation, `verify`, help/docs
2. Timeout primitives + SQLite statement timeout
3. SQL Server login + statement timeouts
4. Tool-level timeout branches (count, validate, summarize, update)
5. Batched read on the backends
6. `result_limits.collect`
7. `render_limited`: truncation messages and rendering
8. Wire single-target query/schema tools
9. Wire fan-out + architecture doc

## Rules for every step
- TDD: write the step's tests first, then the implementation.
- New tests go in new files (`test_query_tools.py`, `test_schema_tools_multitarget.py`,
  `test_validation_tools.py`, `test_update_tools.py` are near the 750-line limit).
- Exit criteria: `run_pylint_check`, `run_pytest_check` (`-n auto`),
  `run_mypy_check`, `run_lint_imports_check` pass; `run_format_code` before commit.
- One commit per step.
