# Step 2 — Shared preflight helpers + migrate `validate_sql` to sqlglot

> Read `pr_info/steps/summary.md` first. Builds on Step 1. Adds the shared,
> dialect-aware analysis helpers to `sql_placeholders.py` and re-bases
> `validate_sql`'s pre-flight on them, adding the fail-closed parse contract.
> `validate_sql` keeps validating writes and does **not** call any read-only gate.

## WHERE
- `src/mcp_tools_sql/utils/sql_placeholders.py` (add shared helpers)
- `src/mcp_tools_sql/validation_tools.py` (re-base preflight)
- `tests/test_validation_tools.py` (update assertions)

## WHAT (new shared helpers in `sql_placeholders.py`)
```python
def to_dialect(backend_name: str) -> str:        # "sqlite"->"sqlite", "mssql"/"pyodbc"->"tsql"
def count_statements(sql: str, dialect: str) -> int:        # raises sqlglot ParseError
def first_statement_kind(sql: str, dialect: str) -> str | None  # "USE"/"SET"/"DECLARE"/None
# re-export sqlglot's ParseError for callers: from sqlglot.errors import ParseError
```
`validation_tools.py` — `_preflight` re-based; `_count_statements` / `_first_keyword`
removed (logic moves to the shared helpers). `_explain` keeps its existing
two-branch (sqlite verbatim / mssql literal-substituted) structure.

## HOW (integration)
- `validation_tools.py` imports `to_dialect`, `count_statements`,
  `first_statement_kind`, `extract_param_names`, `ParseError` from
  `utils.sql_placeholders`. Drop the `import sqlparse` / `from sqlparse import
  tokens` lines and the local `_count_statements`/`_first_keyword`.
- `_preflight(sql, params, dialect)` gains the `dialect` argument (call site has
  `self._backend_name` → `to_dialect(...)`).
- `_SESSION_KEYWORDS = frozenset({"USE","SET","DECLARE"})` stays in
  `validation_tools.py` (validate_sql-specific).

## ALGORITHM (`_preflight`)
```
if sql.strip() == "":            return "Invalid SQL. ValidationError: empty SQL"
try:    n = count_statements(sql, dialect)
except ParseError as e:          return f"Invalid SQL. ParseError: {e}"
if n > 1:                        return "Invalid SQL. ValidationError: multiple statements not supported"
kw = first_statement_kind(sql, dialect)
if kw in _SESSION_KEYWORDS:      return f"Invalid SQL. ValidationError: {kw} statements not supported"
missing = extract_param_names(sql) - (params or {}).keys()
if missing:                      return f"Invalid parameters. ValidationError: missing parameter: {min(missing)}"
return None
```
Shared helper sketch:
```
count_statements(sql, dialect): return len([s for s in sqlglot.parse(sql, read=dialect) if s])
first_statement_kind(sql, dialect):
    root = sqlglot.parse(sql, read=dialect)[0]      # None-safe
    map exp.Use->"USE", exp.Set->"SET", exp.Command(name=="DECLARE")->"DECLARE", else None
```
> Verify how sqlglot/tsql models `DECLARE @x INT` (likely `exp.Command` with
> `this == "DECLARE"`); map accordingly so the existing verdict is preserved.

## DATA
- `_preflight` → `str | None` (verdict or pass-through).
- `to_dialect` → `str`; `count_statements` → `int`; `first_statement_kind` → `str | None`.

## TDD / TESTS (`tests/test_validation_tools.py`)
- **Preserve** the session-keyword verdict tests (`USE`/`SET`/`DECLARE`),
  empty/whitespace, multi-statement, and missing-param tests — same verdict
  strings.
- **Update** `test_mssql_explain_showplan_sequence`: the explained SQL is now
  sqlglot-rendered. Replace the verbatim `"SELECT 1"` expectation with sqlglot's
  render of `SELECT :a` + `{"a":1}` (confirm the rendered literal form; assert
  the SHOWPLAN ON / <rendered> / SHOWPLAN OFF order).
- **Relax** `test_syntax_error`: under fail-closed, `SELEKT …` may surface as
  `Invalid SQL. ParseError: …`. Assert `text.startswith("Invalid SQL. ")` and
  drop the `"OperationalError"` substring check (or branch on whichever sqlglot
  produces).
- Add a **fail-closed** test: clearly unparseable SQL → `Invalid SQL. ParseError: `
  prefix, and `backend.explain` is never called (MagicMock spy, call_count == 0).
- Keep the SQLite success tests unchanged (`Valid.`, plan, UPDATE/DDL not
  executed) — SQLite explain stays verbatim.

## DONE WHEN
- All three checks pass; `validation_tools.py` no longer imports `sqlparse`.
- Single commit: sql_placeholders.py + validation_tools.py + test_validation_tools.py.

## LLM PROMPT
> Implement Step 2 of `pr_info/steps/summary.md` (`pr_info/steps/step_2.md`).
> Add `to_dialect`, `count_statements`, `first_statement_kind` and a `ParseError`
> re-export to `src/mcp_tools_sql/utils/sql_placeholders.py`. Re-base
> `validate_sql`'s `_preflight` in `src/mcp_tools_sql/validation_tools.py` on
> them, removing the local sqlparse-based `_count_statements`/`_first_keyword`
> and adding the fail-closed `Invalid SQL. ParseError: <msg>` contract; keep
> `_explain`'s existing two-branch structure and preserve every existing verdict
> string. Update `tests/test_validation_tools.py` (TDD) per the step: keep
> session-keyword/empty/multi/missing-param tests, fix the MSSQL SHOWPLAN
> assertion to the sqlglot-rendered SQL, relax the syntax-error assertion, and
> add a fail-closed parse test. Use MCP tools only and run pylint, mypy, and the
> unit pytest subset until green. Produce exactly one commit.
