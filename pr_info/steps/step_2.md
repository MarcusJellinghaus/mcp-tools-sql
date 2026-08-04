# Step 2 — `where` validation, table ref, metadata SQL, `COUNT(*)` SQL

Build the front of the pipeline: the fail-closed `where` gate, the dialect table
reference, the static metadata query, and the AST'd filtered `COUNT(*)`. See
`pr_info/steps/summary.md` (§ Execution pipeline steps 1–3, § Static metadata
SQL / AST'd data SQL, § design #3).

## WHERE

- `src/mcp_tools_sql/summarize/sql.py` (extend).
- `tests/summarize/test_sql.py` (extend).

## WHAT

```python
def build_table_ref(schema: str, table: str, dialect: str) -> exp.Table: ...
    # tsql -> db=schema; sqlite -> no db (schema accepted & ignored, decision 20)

def validate_where(
    where: str | None, schema: str, table: str,
    params: dict[str, Any] | None, dialect: str,
) -> tuple[exp.Expression | None, str | None]:
    # returns (predicate_ast, None) on success; (None, error_message) on failure;
    # (None, None) when where is None/blank

def metadata_sql(dialect: str) -> str: ...
    # static per-dialect constant with :schema / :table bound params

def build_count_sql(
    table_ref: exp.Table, predicate: exp.Expression | None, dialect: str,
) -> str: ...
```

## HOW

- Import from `mcp_tools_sql.utils.sql_placeholders`: `basic_preflight`,
  `read_only_violation`. Import `sqlglot` / `sqlglot.exp`.
- `validate_where` synthesises `SELECT 1 FROM <schema.table> WHERE <where>`
  (rendered from `build_table_ref`), runs **`basic_preflight`** (reused
  unchanged — catches empty/multi-statement/unbound `:name`), then
  `read_only_violation`, then re-extracts the `where` arg from the re-parsed
  statement (never echo user text). Any verdict string becomes the error return.
- `metadata_sql` is a plain string constant per dialect — it injects only bound
  values, so no AST:
  - tsql: `SELECT COLUMN_NAME AS name, DATA_TYPE AS type, ORDINAL_POSITION AS ordinal FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = :schema AND TABLE_NAME = :table ORDER BY ORDINAL_POSITION`
  - sqlite: `SELECT name, type, cid AS ordinal FROM pragma_table_info(:table) ORDER BY cid`
- `build_count_sql` builds `SELECT COUNT(*) AS row_count FROM <table_ref>` and
  `.where(predicate)` when present, rendered via `.sql(dialect=...)`.

## ALGORITHM (`validate_where`)

```
if not where or where.strip() == "": return (None, None)
probe = f"SELECT 1 FROM {table_ref.sql(dialect)} WHERE {where}"
verdict = basic_preflight(probe, params, dialect);  if verdict: return (None, verdict)
verdict = read_only_violation(probe, dialect);      if verdict: return (None, verdict)
predicate = sqlglot.parse_one(probe, read=dialect).args["where"].this
return (predicate, None)
```

## DATA

- `build_table_ref` → `exp.Table`.
- `validate_where` → `(exp.Expression | None, str | None)`.
- `metadata_sql` → `str`.
- `build_count_sql` → rendered `str`.

## TESTS

- Rendered-SQL assertions per dialect:
  - `build_count_sql` with/without predicate: `SELECT COUNT(*) AS row_count FROM [dbo].[t]` (tsql) vs `FROM "t"` (sqlite); predicate appears in `WHERE`.
  - `build_table_ref`: tsql includes `[schema].[t]`; sqlite omits schema.
  - `metadata_sql`: contains `INFORMATION_SCHEMA.COLUMNS` (tsql) /
    `pragma_table_info(:table)` (sqlite).
- `validate_where`: `None`/blank → `(None, None)`; a write predicate
  (`1=1); DROP TABLE t --` style / subquery with `DELETE`) → error via
  `read_only_violation`; unbound `:x` without params → `basic_preflight`
  missing-parameter verdict; a valid `status = :s` with `params={"s":...}` →
  returns a predicate AST (assert on its rendered `.sql`).

## COMMIT

`feat(summarize): add where validation, table ref, metadata and count SQL`

## PROMPT

> Implement Step 2 from `pr_info/steps/step_2.md` (context in
> `pr_info/steps/summary.md`). Add `build_table_ref`, `validate_where`,
> `metadata_sql`, and `build_count_sql` to `summarize/sql.py`. Reuse
> `basic_preflight` and `read_only_violation` from `utils.sql_placeholders`
> unchanged; re-render the predicate from the AST rather than echoing user text.
> Metadata SQL is a static per-dialect string (bound `:schema`/`:table` only);
> the count query is sqlglot-built and rendered with `.sql(dialect=...)`. Write
> rendered-SQL assertions per dialect first. Run pylint/pytest/mypy; one commit.
