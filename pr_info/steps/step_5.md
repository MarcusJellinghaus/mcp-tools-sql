# Step 5 — `count_records` tool: module + registration + architecture config

> Read `pr_info/steps/summary.md` first. Final step. Wires Steps 1–4 into the
> new built-in `count_records` tool, registers it, and updates the architecture
> contracts. Includes the SQLite end-to-end count tests (the real placeholder
> round-trip verification).

## WHERE
- `src/mcp_tools_sql/count_tools.py` (new — sibling of `validation_tools.py`)
- `src/mcp_tools_sql/server.py` (register)
- `src/mcp_tools_sql/schema_tools.py` (`PROGRAMMATIC_BUILTIN_TOOLS`)
- `.importlinter`, `tach.toml` (add `count_tools` to the tool layer)
- `tests/test_count_tools.py` (new)
- `tests/test_server.py` (registration / builtin-count)

## WHAT
```python
class CountTools:
    def __init__(self, backend: DatabaseBackend, backend_name: str) -> None: ...
    def register(self, mcp: FastMCP) -> None: ...
        # registers async def count_records(sql, params=None) -> str
```
Tool signature (MCP):
```python
async def count_records(
    sql: Annotated[str, Field(description="The read-only SELECT to count.")],
    params: Annotated[dict[str, Any] | None,
                      Field(description="Bound values for :name placeholders.")] = None,
) -> str: ...
```

## HOW (integration)
- `count_tools.py` imports: `log_tool_call`; from `utils.sql_placeholders`:
  `to_dialect`, `count_statements`, `first_statement_kind` (unused — skip),
  `extract_param_names`, `read_only_violation`, `build_count_query`, `ParseError`;
  reuse the empty/multi/missing-param preflight via a shared helper. To avoid a
  sibling import of `validation_tools._preflight`, factor the **basic** preflight
  (empty / fail-closed parse / multi-statement / missing-param — no session
  keywords) into `utils.sql_placeholders.basic_preflight(sql, params, dialect)`
  and have both `validation_tools` and `count_tools` call it. (Small refactor of
  Step 2's `_preflight` to delegate to it — keep validate_sql's session-keyword
  check on top.)
- `server.py`: in `_register_builtin_tools`, add
  `CountTools(self._backend, self._backend_name).register(self._mcp)` (after
  ValidationTools; **not** gated by `allow_updates`). Import `CountTools`.
- `schema_tools.py`: `PROGRAMMATIC_BUILTIN_TOOLS = ("validate_sql", "count_records")`.
- `.importlinter`: add `mcp_tools_sql.count_tools` to the tool-layer line
  (`... | mcp_tools_sql.validation_tools | mcp_tools_sql.count_tools`).
- `tach.toml`: add a `[[modules]]` entry for `mcp_tools_sql.count_tools`
  (layer `tool_implementation`, `depends_on` backends/config/formatting/
  tool_logging/tool_builder/utils), and add it to `server`'s `depends_on`.

## ALGORITHM (`count_records` body)
```
async with log_tool_call("count_records", params or {}, sql=sql) as rec:
    rec.record(rows=1, cols=1)
    dialect = to_dialect(backend_name)
    verdict = basic_preflight(sql, params, dialect)          # empty/parse/multi/missing
    if verdict: return verdict
    violation = read_only_violation(sql, dialect)
    if violation: return violation
    if dialect == "tsql" and <root has WITH>:                # leading CTE
        return "CTE (WITH) queries can't be counted on SQL Server — the count wrapper doesn't support them."
    wrapped = build_count_query(sql, dialect)
    try:
        rows = backend.execute_readonly_query(wrapped, params)
    except <same exc map as validate_sql>: return mapped verdict
    return str(rows[0]["row_count"])
```
- Exception mapping mirrors `validate_sql` (`_INVALID_SQL_EXC` →
  `Invalid SQL.`; `KeyError/TypeError/ValueError` → `Invalid parameters.`;
  `RuntimeError` → `Database connection error.`; else `Unexpected error.`).
- The leading-`WITH` check uses the parsed root (`sqlglot.parse_one(sql,
  read="tsql").args.get("with")`); can be a tiny helper in the shared module.

## DATA
- Returns a **bare number string** (e.g. `"42"`). Error paths return the labelled
  verdict strings (same style as `validate_sql`).

## TOOL DESCRIPTION (explicit about execution)
> "Count the rows a read-only SELECT would return. Executes a
> `SELECT COUNT(*)` wrapper around your query (read-only); rejects any statement
> that is not read-only (no INSERT/UPDATE/DELETE/DDL/SELECT…INTO). Returns the
> count as a plain number. Supports `:name` placeholders via `params`. Unlike
> validate_sql, this tool executes the wrapped count query."

## TDD / TESTS
`tests/test_count_tools.py` (SQLite e2e via `sqlite_db` fixture, same MCP-client
pattern as `test_validation_tools.py`):
- `SELECT * FROM customers` → `"2"`; `SELECT * FROM orders` → `"3"`.
- `WHERE` filter → correct subset count.
- `:name` param: `SELECT * FROM orders WHERE status = :s`, `{"s":"pending"}` → `"2"`.
- Read-only gate rejections: `UPDATE …`, `INSERT …`, `DELETE …`, `DROP TABLE …`,
  `SELECT … INTO …` → `Not read-only.` verdict, and **no rows modified**.
- Preflight parity: empty → `empty SQL`; `SELECT 1; SELECT 2` → multiple
  statements; missing `:name` param → missing parameter.
- Fail-closed: unparseable SQL → `Invalid SQL. ParseError: ` prefix.
- Deterministic MSSQL leading-`WITH`: construct `CountTools(mock_backend, "mssql")`
  (MagicMock backend, as in `test_validation_tools.py`), call with
  `WITH x AS (SELECT 1) SELECT * FROM x` → the precise CTE rejection message,
  and assert `execute_readonly_query` was **not** called.

`tests/test_server.py`:
- Add a test that `_register_builtin_tools()` registers `count_records`.
- The existing `builtin_tools=N` counter test stays green automatically because
  `PROGRAMMATIC_BUILTIN_TOOLS` now includes `count_records`.

## VERIFICATION
- Run `run_lint_imports_check` and `run_tach_check` — both must pass with the new
  module wired in.

## DONE WHEN
- All three code checks + import-linter + tach pass.
- Single commit: count_tools.py + server.py + schema_tools.py + .importlinter +
  tach.toml + test_count_tools.py + test_server.py (+ the small `basic_preflight`
  refactor in sql_placeholders.py / validation_tools.py).

## LLM PROMPT
> Implement Step 5 of `pr_info/steps/summary.md` (`pr_info/steps/step_5.md`).
> Create `src/mcp_tools_sql/count_tools.py` with a `CountTools` class registering
> an async `count_records(sql, params=None) -> str` tool: basic preflight
> (factor `basic_preflight` into `utils.sql_placeholders` and reuse it from
> `validation_tools` too), then `read_only_violation`, then the deterministic
> MSSQL leading-`WITH` rejection, then `build_count_query` + 
> `backend.execute_readonly_query`, returning `str(rows[0]["row_count"])` with
> the same exception mapping as `validate_sql`. Register it in
> `server._register_builtin_tools` (not gated by `allow_updates`), add
> `"count_records"` to `PROGRAMMATIC_BUILTIN_TOOLS`, and add `count_tools` to
> `.importlinter` and `tach.toml`. Write the TDD tests in
> `tests/test_count_tools.py` (SQLite e2e counts, `:name` params, gate
> rejections, preflight parity, fail-closed, mock-backend MSSQL `WITH`
> rejection) and a registration test in `tests/test_server.py`. Use MCP tools
> only; run pylint, mypy, the unit pytest subset, `run_lint_imports_check`, and
> `run_tach_check` until all pass. Produce exactly one commit.
