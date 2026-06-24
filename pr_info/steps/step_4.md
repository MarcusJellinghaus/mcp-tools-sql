# Step 4 — Read-only AST gate + COUNT-wrap helpers (pure functions)

> Read `pr_info/steps/summary.md` first. Builds on Steps 1–2. Adds two pure,
> dialect-aware helpers to `sql_placeholders.py`, fully unit-testable with no DB.
> These are the primary security boundary (gate) and the count wrapper used by
> `count_records` (Step 5).

## WHERE
- `src/mcp_tools_sql/utils/sql_placeholders.py` (add two helpers)
- `tests/test_sql_placeholders.py` (add unit tests; or a focused new test class)

## WHAT
```python
def read_only_violation(sql: str, dialect: str) -> str | None:
    """Return a rejection message if the statement is not provably read-only,
    else None. Raises sqlglot ParseError on unparseable SQL (caller fail-closes)."""

def build_count_query(sql: str, dialect: str) -> str:
    """Render SELECT COUNT(*) AS row_count FROM (<sql>) AS count_sub for `dialect`.
    Raises sqlglot ParseError on unparseable SQL."""

# small module constants:
_WRITE_NODES = (exp.Insert, exp.Update, exp.Delete, exp.Merge,
                exp.Create, exp.Drop, exp.Alter, exp.TruncateTable)

# STRICT read-only root allow-list (fail-closed: reject any root NOT listed).
# Accepted roots per the issue:
#   SQLite:    SELECT / WITH / VALUES   (WITH...SELECT parses as a Select
#              carrying a `with` arg, so exp.Select covers it)
#   MSSQL/tsql: SELECT / WITH (the leading-CTE case is rejected deterministically
#              downstream in count_records, Step 5)
# The exact exp.* node-type names are pinned empirically during implementation
# (e.g. whether exp.Union / exp.Values appear as roots), but "reject unknown
# roots" is the FIXED contract — do NOT leave a trailing `...` catch-all.
_READONLY_ROOTS = (exp.Select, exp.Union, exp.Values)   # adjust per empirical check
```

## HOW (integration)
- Imports already present from Step 1 (`sqlglot`, `exp`). No new external deps.
- `read_only_violation` and `build_count_query` are called only by
  `count_tools.py` (Step 5); they live in the shared module per the issue's
  module-layout decision.

## ALGORITHM
```
read_only_violation(sql, dialect):
    root = sqlglot.parse_one(sql, read=dialect)          # ParseError -> propagate
    if root.find(*_WRITE_NODES) is not None:
        return "Not read-only. <node-kind> statements are not permitted."
    # SELECT ... INTO creates a table on MSSQL
    if any(s.args.get("into") for s in root.find_all(exp.Select)):
        return "Not read-only. SELECT ... INTO is not permitted."
    # root must itself be a read-only construct — STRICT, fail-closed allow-list.
    # Reject any root node type NOT explicitly listed below.
    if not isinstance(root, _READONLY_ROOTS):
        return "Not read-only. Only SELECT/WITH/VALUES queries can be counted."
    return None

build_count_query(sql, dialect):
    inner = sqlglot.parse_one(sql, read=dialect)
    wrapped = exp.select(exp.alias_(exp.Count(this=exp.Star()), "row_count")) \
                 .from_(inner.subquery("count_sub"))
    return wrapped.sql(dialect=dialect)
```
Notes:
- `root.find(*_WRITE_NODES)` walks the whole tree, so a data-modifying CTE body
  (`WITH x AS (DELETE …) …`) is caught by the `exp.Delete` node inside it.
- Confirm the exact read-only root node set against sqlglot per dialect and pin
  `_READONLY_ROOTS` to the observed classes (`exp.Subquery` may wrap;
  `WITH ... SELECT` parses as a `Select` carrying a `with` arg, so `exp.Select`
  covers it — verify and adjust the tuple). The allow-list is **fail-closed**:
  any root not in `_READONLY_ROOTS` is rejected; never widen it to a catch-all.
- Keep messages concise/precise; they are returned verbatim by the tool.

## DATA
- `read_only_violation` → `str | None`.
- `build_count_query` → `str` (renders
  `SELECT COUNT(*) AS row_count FROM (<sql>) AS count_sub`, dialect-targeted,
  placeholders preserved).

## TDD / TESTS (`tests/test_sql_placeholders.py`)
`read_only_violation` (use `dialect="sqlite"` unless noted):
- `SELECT * FROM t` → `None`; `WITH x AS (SELECT 1) SELECT * FROM x` → `None`;
  `VALUES (1),(2)` → `None`.
- Rejects: `INSERT …`, `UPDATE …`, `DELETE …`, `DROP TABLE t`, `CREATE TABLE …`,
  `ALTER TABLE …`, `TRUNCATE TABLE t`, `MERGE …` → non-None message.
- `SELECT * INTO new_t FROM t` (dialect `tsql`) → non-None.
- Data-modifying CTE (`tsql`: `WITH x AS (...) DELETE …`; verify it parses) →
  non-None.
- **Fail-closed root**: a parseable statement whose root is not in
  `_READONLY_ROOTS` (e.g. a bare `EXPLAIN …` / `PRAGMA …`, whichever sqlglot
  parses to a non-listed root) → non-None — proving unknown roots are rejected.
`build_count_query`:
- `SELECT * FROM customers` (sqlite) renders to the expected wrapper string
  (assert it contains `COUNT(*)`, `AS row_count`, `AS count_sub`).
- With placeholder: `SELECT * FROM t WHERE id = :id` (sqlite) → rendered wrapper
  still contains a bindable `:id`; (tsql) render is valid T-SQL.

## DONE WHEN
- All three checks pass.
- Single commit: sql_placeholders.py + test_sql_placeholders.py additions.

## LLM PROMPT
> Implement Step 4 of `pr_info/steps/summary.md` (`pr_info/steps/step_4.md`).
> Add `read_only_violation(sql, dialect)` and `build_count_query(sql, dialect)`
> (plus the `_WRITE_NODES` tuple) to
> `src/mcp_tools_sql/utils/sql_placeholders.py`, using sqlglot AST inspection —
> reject any write node anywhere in the tree, `SELECT ... INTO`, and
> non-read-only roots; build the COUNT wrapper as an AST and render per dialect.
> Confirm the read-only root node set and the placeholder round-trip empirically,
> then write TDD unit tests in `tests/test_sql_placeholders.py` covering the
> accepted/rejected constructs and the rendered wrapper (including placeholder
> preservation). Use MCP tools only; run pylint, mypy, and the unit pytest
> subset until green. Produce exactly one commit.
