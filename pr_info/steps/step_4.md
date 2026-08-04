# Step 4 — Value-list SQL (top-values + sample-values)

Build the per-column `GROUP BY` (deep view only) whose *shape* is chosen by
duplication. See `pr_info/steps/summary.md` (§ Execution pipeline step 5,
§ invariants: total ordering, `n` clamp).

## WHERE

- `src/mcp_tools_sql/summarize/sql.py` (extend).
- `tests/summarize/test_sql.py` (extend).

## WHAT

```python
VALUE_LIST_HARD_CAP: int = 50
VALUE_LIST_MIN: int = 1

def clamp_n(n: int) -> tuple[int, str]: ...
    # returns (max(1, min(n, 50)), note) — note non-empty only when clamped
    # (clamped in **either** direction)

def build_value_list_sql(
    col: ColumnMeta,
    table_ref: exp.Table,
    predicate: exp.Expression | None,
    n: int,
    dialect: str,
    *, kind: Literal["top", "sample"],
) -> str: ...
```

## HOW

- Column ref: `exp.column(exp.to_identifier(col.name, quoted=True))`.
- `kind == "top"`: `SELECT c AS value, COUNT(*) AS freq FROM t [WHERE p]
  GROUP BY c ORDER BY COUNT(*) DESC, c ASC LIMIT n`. `NULL` groups as an
  ordinary row (no special handling). Ordering **must** carry the `value ASC`
  tiebreak for total determinism.
- `kind == "sample"`: `SELECT DISTINCT c AS value FROM t WHERE c IS NOT NULL
  [AND p] ORDER BY c ASC LIMIT n` (no `freq` column — frequency is uninformative
  when every count is 1). **`NULL` is excluded** (unlike the `top` kind, which
  ranks `NULL` as a row): the sample header reads `N of D distinct` where
  `D = COUNT(DISTINCT c)` excludes nulls, so a returned `NULL` row would make
  `len(values)` exceed `D` and render the nonsensical `N of D` with `N > D` for
  a unique-non-null column that also holds nulls.
- **Build the null test as `exp.Is(this=ref, expression=exp.Null(),
  negate=True)`**, which renders literal `"c" IS NOT NULL` on both dialects.
  Do **not** use `ref.is_(exp.null()).not_()`: that builds
  `exp.Not(exp.Is(...))` and renders `NOT "c" IS NULL` (sqlglot's
  `Generator.not_sql` is `f"NOT {this}"`, with no sqlite/tsql override).
  Semantically equivalent, but it would contradict the `WHERE c IS NOT NULL`
  wording above, the ALGORITHM comment, and the TEST assertion below.
- Limit via sqlglot `.limit(n)` so the renderer emits `LIMIT n` (sqlite) /
  `TOP n` (tsql) automatically. Do **not** call this for `other`-category
  columns (caller skips them — LOB cannot be grouped).
- The caller (step 7) picks `kind` from scalar stats:
  `distinct < non_null → "top"`, `distinct == non_null → "sample"`.
- `clamp_n` clamps in **both** directions: `VALUE_LIST_HARD_CAP` (50) above and
  `VALUE_LIST_MIN` (1) below. The lower bound is not cosmetic — `n=0` would emit
  an empty value list under a `top values:` header, and `n<0` renders
  `TOP -1`, which SQL Server rejects outright. Both out-of-range directions
  produce a non-empty note so the user sees what was applied.

## ALGORITHM (`build_value_list_sql`)

```
ref = column(quoted(col.name))
if kind == "top":
    q = exp.select(alias(ref,"value"), alias(Count(Star()),"freq")).from_(t)
    q = q.group_by(ref).order_by(Count(Star()).desc(), ref.asc())
else:
    q = exp.select(alias(ref,"value")).distinct().from_(t).order_by(ref.asc())
    q = q.where(exp.Is(this=ref, expression=exp.Null(), negate=True))  # c IS NOT NULL
if predicate: q = q.where(predicate)   # sqlglot .where() AND-combines
return q.limit(n).sql(dialect=dialect)
```

## DATA

- `clamp_n` → `(int, str)`.
- `build_value_list_sql` → rendered `str` returning `(value[, freq])` rows.

## TESTS

Rendered-SQL per dialect:

- top: contains `GROUP BY`, `ORDER BY COUNT(*) DESC` **and** the `value`/column
  ASC tiebreak; `LIMIT 20` (sqlite) vs `TOP 20` (tsql).
- sample: `SELECT DISTINCT`, no `freq`, `WHERE c IS NOT NULL` (NULL excluded —
  assert the literal `IS NOT NULL` text, which pins the `exp.Is(..., negate=
  True)` construction against a `NOT … IS NULL` regression), `ORDER BY` the
  column, correct limit; with a predicate the two conditions are AND-combined.
- predicate embedded in `WHERE` for both kinds.
- `clamp_n(20) == (20, "")`; `clamp_n(500)[0] == 50` with a non-empty note;
  `clamp_n(0)[0] == 1` and `clamp_n(-5)[0] == 1`, both with a non-empty note
  (lower bound — no empty `top values:` header, no `TOP -1`).

## COMMIT

`feat(summarize): add duplication-driven value-list SQL generation`

## PROMPT

> Implement Step 4 from `pr_info/steps/step_4.md` (context in
> `pr_info/steps/summary.md`). Add `clamp_n` and `build_value_list_sql`
> (`kind="top"|"sample"`) to `summarize/sql.py`. Top lists are
> `COUNT(*) DESC, value ASC` (total order, `NULL` as a row); sample lists are
> `SELECT DISTINCT … ORDER BY value` with no freq column. Use sqlglot `.limit`
> so `TOP n`/`LIMIT n` fall out per dialect; clamp `n` into `[1, 50]` (both
> bounds — `n<=0` must not produce an empty list or `TOP -1`). Write
> rendered-SQL-per-dialect assertions first. Run pylint/pytest/mypy; one commit.
