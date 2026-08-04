# Step 3 — Scalar-aggregate pass SQL + `ColumnMeta`

Build the single `SELECT` that computes every statistic for every profiled
column in one table scan, dispatched per category. See
`pr_info/steps/summary.md` (§ Shared data structures, § Type categories &
statistics, § invariants).

## WHERE

- `src/mcp_tools_sql/summarize/sql.py` (extend).
- `tests/summarize/test_sql.py` (extend).

## WHAT

```python
@dataclass(frozen=True)
class ColumnMeta:
    name: str
    declared_type: str
    category: Category
    ordinal: int

def build_scalar_sql(
    columns: list[ColumnMeta],
    table_ref: exp.Table,
    predicate: exp.Expression | None,
    dialect: str,
    *, include_distinct: bool,
) -> str: ...

# internal per-category expression builders, each returning list[exp.Alias]:
def _numeric_exprs(idx, col_ref, decl_type, dialect, include_distinct) -> list[exp.Alias]: ...
def _temporal_exprs(...) -> list[exp.Alias]: ...
def _string_exprs(...) -> list[exp.Alias]: ...
def _boolean_exprs(...) -> list[exp.Alias]: ...
def _other_exprs(idx, col_ref, decl_type, dialect, include_distinct) -> list[exp.Alias]: ...
#   every builder shares this 5-arg signature so the ALGORITHM dispatch can call
#   them uniformly; _other_exprs ignores decl_type / include_distinct (no
#   distinct, no min/max for LOB), but must still accept them.
```

## HOW

- Column ref: `exp.column(exp.to_identifier(meta.name, quoted=True))`.
- Each aggregate aliased `c{idx}__{stat}` (e.g. `c0__nonnull`, `c0__distinct`,
  `c0__min`, `c0__mean`, `c0__sum`, `c0__zero`, `c0__neg`, `c0__empty`,
  `c0__len_min`, `c0__len_avg`, `c0__true`, `c0__false`, `c0__size_max`).
  `nulls` is derived in the renderer as `rows - non_null`, so it is **not** a
  scalar column.
- Build one `exp.select(*all_aliases).from_(table_ref)`; `.where(predicate)`
  when present. Render `.sql(dialect=...)`.
- Category rules (§ summary table):
  - **numeric**: `min`,`max`, `mean = AVG(CAST(c AS FLOAT))`,
    `sum = SUM(CAST(c AS BIGINT))` when tsql **and** integer-like declared type
    (guards the `int` overflow past 2^31-1); for **non-integer** numerics
    (decimal/money/float) leave the argument **uncast** — `SUM(c)` — since only
    integers overflow and a FLOAT cast is lossy on exact decimals; on sqlite
    `SUM(c)` uncast throughout; `zero = COUNT(CASE WHEN c = 0 …)`,
    `neg = COUNT(CASE WHEN c < 0 …)`.
  - **string**: `empty = COUNT(CASE WHEN LTRIM(RTRIM(c)) = '' …)`; lengths via
    `exp.Length` (renders `LENGTH` on sqlite, `LEN` on tsql), `len_avg` cast to
    FLOAT.
  - **boolean**: `true = COUNT(CASE WHEN c = 1 …)`, `false = … c = 0 …`.
  - **other**: **no distinct, no min/max, no value list**. tsql only:
    `size_min/max/avg = DATALENGTH(c)` (legal on LOB). sqlite other: rows/nulls
    only.
  - `non_null = COUNT(c)` for every category; `distinct = COUNT(DISTINCT c)`
    only when `include_distinct` **and** category != other.

## ALGORITHM (`build_scalar_sql`)

```
aliases = []
for i, m in enumerate(columns):
    ref = column(quoted(m.name))
    aliases += {numeric:_numeric_exprs, temporal:_temporal_exprs,
                string:_string_exprs, boolean:_boolean_exprs,
                other:_other_exprs}[m.category](i, ref, m.declared_type,
                                                dialect, include_distinct)
sel = exp.select(*aliases).from_(table_ref)
if predicate: sel = sel.where(predicate)
return sel.sql(dialect=dialect)
```

## DATA

`build_scalar_sql` → one rendered `str` producing a **single result row**.
`ColumnMeta` is the metadata carrier consumed by every downstream step.

## TESTS

Rendered-SQL assertions per dialect (build `ColumnMeta`s directly):

- numeric tsql: `AVG(CAST(... AS FLOAT))` and `SUM(CAST(... AS BIGINT))`
  present; sqlite uses `SUM` without BIGINT cast.
- string: `LEN(` on tsql vs `LENGTH(` on sqlite; `LTRIM(RTRIM(` empty predicate.
- other/LOB tsql: `DATALENGTH(` present; **no** `COUNT(DISTINCT` and **no**
  `MIN(`/`MAX(` for that column.
- `include_distinct=False` omits every `COUNT(DISTINCT`; `True` includes it for
  non-other columns.
- alias scheme: assert `AS c0__` / `AS c1__` prefixes so the assembler contract
  is pinned.

## COMMIT

`feat(summarize): add scalar-aggregate pass SQL generation`

## PROMPT

> Implement Step 3 from `pr_info/steps/step_3.md` (context in
> `pr_info/steps/summary.md`). Add the `ColumnMeta` dataclass and
> `build_scalar_sql` plus per-category expression builders to `summarize/sql.py`,
> aliasing every aggregate `c{idx}__{stat}` and producing one single-row SELECT.
> Honour the dialect casts (`AVG(CAST … FLOAT)`, `SUM(CAST … BIGINT)` on T-SQL
> ints), `exp.Length` for string chars, `DATALENGTH` for other/binary on T-SQL,
> the LOB exclusion (no distinct/min/max/value-list for `other`), and the
> `include_distinct` gate. Write rendered-SQL-per-dialect assertions first. Run
> pylint/pytest/mypy; one commit.
