# Step 5 — Deep-view renderer + `ColumnProfile`

Render one full labelled block per profiled column from a `ColumnProfile`.
Pure formatting — no DB. See `pr_info/steps/summary.md` (§ Shared data
structures, § invariants) and the issue's "Deep-view rendering" examples.

## WHERE

- Create `src/mcp_tools_sql/summarize/render.py`.
- Create `tests/summarize/test_render.py`.

## WHAT

```python
@dataclass(frozen=True)
class ColumnProfile:
    meta: ColumnMeta                      # imported from summarize.sql
    rows: int
    non_null: int
    distinct: int | None
    stats: dict[str, Any]
    values: list[tuple[Any, ...]] | None  # (value, freq) for top; (value,) for sample
    value_kind: Literal["top", "sample", "none"]

def render_deep(profiles: list[ColumnProfile], n: int) -> str: ...

# internal helpers:
def _fmt_int(n: int) -> str                     # thousands separators
def _fmt_pct(part: int, whole: int) -> str      # "(2.4%)", guards whole == 0
def _truncate(value: Any) -> str                # 60-char display cap + "…"
def _render_block(p: ColumnProfile, n: int) -> str
def _render_values(p: ColumnProfile, n: int) -> list[str]
```

## HOW

- Header line: `name  (declared_type, category)`.
- Stat lines grouped per category, thousands-separated, percentages beside
  counts. `nulls = rows - non_null`; `empty`/`nulls` show `(x.y%)` of `rows`.
- Value list (never for `value_kind == "none"`):
  - **top**: rows `value  freq  (pct)`, `pct` of `rows`; then a remainder line
    `… {distinct - shown_non_null} other values, {rows - shown_rows} rows (pct)`
    — pure arithmetic from `distinct` and returned counts. `NULL` printed
    literally as a value row.
  - **sample**: header `sample values (N of D distinct — every value unique):`
    then values only, no counts.
- Display-truncate each value via `_truncate`; **counts stay exact**.

## ALGORITHM (`_render_values`, top)

```
lines = ["  top values:"]
shown_rows = sum(freq); shown_nonnull_distinct = len([v for v in values if v is not NULL])
for value, freq in values: lines.append(f"    {_truncate(value)}  {_fmt_int(freq)}  {_fmt_pct(freq, rows)}")
rem_vals = distinct - shown_nonnull_distinct
rem_rows = rows - shown_rows                      # `rows` is the total filtered COUNT(*) (p.rows); denominator for every % is this same total
if rem_vals > 0: lines.append(f"    … {rem_vals} other values, {_fmt_int(rem_rows)} rows {_fmt_pct(rem_rows, rows)}")
return lines
```

(Note: remainder is *distinct-non-null minus non-null values shown*; because
`COUNT(DISTINCT)` excludes nulls while the list ranks `NULL` as a row, exclude
the `NULL` entry from the distinct-shown tally. Pin the exact numbers with a
test built from the issue's `customer_city` example.)

## DATA

`render_deep` → a single `str` (blank-line-separated blocks). Renderers never
touch a backend.

## TESTS (`tests/summarize/test_render.py`)

Hand-build `ColumnProfile`s (no DB) and assert on rendered text:

- string column with duplicates → matches the issue's `customer_city` block
  (nulls/empty/distinct line, `top values`, remainder line with correct % ).
- near-unique column (`distinct == non_null - 1`) → the duplicate surfaces at
  the top; remainder line present.
- perfectly unique (`distinct == non_null`) → `sample values (N of D distinct —
  every value unique)` header, no counts.
- numeric block: min/max/mean/sum/zero/neg present, thousands separators.
- `_truncate` caps at 60 chars + `…`; `_fmt_pct(_, 0)` does not divide by zero.

## COMMIT

`feat(summarize): add deep-view renderer`

## PROMPT

> Implement Step 5 from `pr_info/steps/step_5.md` (context in
> `pr_info/steps/summary.md`). Create `summarize/render.py` with the
> `ColumnProfile` dataclass and `render_deep`, plus the int/pct/truncate helpers
> and per-category block rendering. Match the issue's deep-view examples exactly
> (labelled lines, thousands separators, top-vs-sample value lists, arithmetic
> remainder line, 60-char value truncation with exact counts). Test against
> hand-built `ColumnProfile`s — no DB. Run pylint/pytest/mypy; one commit.
