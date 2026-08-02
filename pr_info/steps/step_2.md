# Step 2 — Prereq: `build_count_query` strips `ORDER BY`

See `pr_info/steps/summary.md` → "Prerequisite bug fixes" (item 2).

## WHERE
- `src/mcp_tools_sql/utils/sql_placeholders.py`
- Tests: `tests/test_sql_placeholders.py`

## WHAT
`build_count_query(sql, dialect)` must drop the statement-level `ORDER BY` of the
inner query before wrapping it in the `COUNT(*)` derived table. `COUNT(*)` is
order-independent, so this is semantically free and fixes T-SQL error 1033
("ORDER BY invalid in ... derived tables ... unless TOP/OFFSET/FOR XML").

## HOW
After parsing `inner = sqlglot.parse_one(sql, read=dialect)`, remove the `order`
arg from the inner root before building the `exp.Subquery`.

## ALGORITHM
```
inner = sqlglot.parse_one(sql, read=dialect)
inner.set("order", None)                       # drop statement-level ORDER BY
count_sub = exp.Subquery(this=inner, alias=... "count_sub")
wrapped = exp.select(COUNT(*) AS row_count).from_(count_sub)
return wrapped.sql(dialect=dialect)
```

## DATA
Unchanged: returns the rendered count query string.

## TESTS (write first)
- `build_count_query("SELECT TABLE_NAME AS name FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = :schema ORDER BY name", "tsql")`
  renders **without** `ORDER BY` inside the subquery and keeps the `:schema`
  placeholder bindable.
- The same input under `dialect="sqlite"` also drops `ORDER BY`.
- A query with no `ORDER BY` is unchanged apart from the wrapper (regression).
- Qualified names (`sales.dbo.orders`) still preserved in the wrapper.

## LLM PROMPT
> Implement Step 2 from `pr_info/steps/step_2.md` (context in
> `pr_info/steps/summary.md`). In `build_count_query` (utils/sql_placeholders.py),
> strip the statement-level `ORDER BY` from the inner query via
> `inner.set("order", None)` before wrapping. Write tests first asserting the
> rendered count query has no `ORDER BY` in the derived table, for both `tsql` and
> `sqlite`, and that placeholders/qualified names survive. Run pylint, pytest
> (`-n auto` + unit markers), and mypy via the MCP tools; all green. One commit.
