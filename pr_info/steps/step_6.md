# Step 6 — Triage renderer + messages + view dispatch

Add the compact triage view, the zero-row / unknown-column messages, and the
top-level dispatcher that chooses triage vs deep. Still pure formatting — no DB.
See `pr_info/steps/summary.md` (§ Execution pipeline two-tier view, § invariants
zero-rows / column cap).

## WHERE

- `src/mcp_tools_sql/summarize/render.py` (extend).
- `tests/summarize/test_render.py` (extend).

## WHAT

```python
TRIAGE_THRESHOLD: int = 15
COLUMN_CAP: int = 50

def render_triage(profiles: list[ColumnProfile], total_columns: int,
                  distinct_gated: bool) -> str: ...

def render_summary(profiles: list[ColumnProfile], total_columns: int,
                   n: int, distinct_gated: bool) -> str: ...
    # dispatch: len(profiles) > 15 -> triage else deep

def empty_table_message(schema: str, table: str) -> str: ...
def empty_filter_message(total_rows: int) -> str: ...
def unknown_columns_message(bad: list[str], available: list[str]) -> str: ...
def column_cap_footer(shown: int, total: int) -> str: ...
```

## HOW

- `render_triage`: one row per column via `format_rows` (import from
  `mcp_tools_sql.formatting`) with keys
  `{name, type, null_pct, distinct, min, max}`. `distinct` shows `—` (or the
  gate note) when `distinct_gated`. Append `column_cap_footer` when
  `total_columns > len(profiles)`, plus a footer hint that a narrowed `columns=`
  call yields the deep block. When gated, state the 1M-row reason in the footer.
- `render_summary`: `render_triage` when `len(profiles) > TRIAGE_THRESHOLD`,
  else `render_deep(profiles, n)`. A 1-column call renders the same deep block
  as one of 10 (no focus tier).
- Messages (exact wording from the issue):
  - empty table → `Table {schema}.{table} is empty (0 rows). Use read_columns
    for its column definitions.`
  - empty filter → `No rows match the where predicate (table has {N} rows).`
  - unknown columns → `Unknown column(s): {bad}. Available: {available…}` (echo
    declared casing).
  - column cap → `Showing 50 of {N} columns. Use columns= to select others.`

## ALGORITHM (`render_summary`)

```
if not profiles: return ...        # caller handles zero-rows before this
if len(profiles) > TRIAGE_THRESHOLD: return render_triage(profiles, total_columns, distinct_gated)
return render_deep(profiles, n)
```

## DATA

All functions return `str`.

## TESTS

- 16 profiles → triage (one line each, no value lists); 15 → deep blocks.
- triage with `total_columns=412, len=50` → cap footer
  `Showing 50 of 412 columns.`; with `distinct_gated=True` → gate reason in
  footer and `distinct` column shows the gated marker.
- each message renders the exact issue wording; `unknown_columns_message`
  echoes declared casing and lists availables.
- 1-column list → deep block (not a special tier).

## COMMIT

`feat(summarize): add triage renderer, messages and view dispatch`

## PROMPT

> Implement Step 6 from `pr_info/steps/step_6.md` (context in
> `pr_info/steps/summary.md`). Extend `summarize/render.py` with `render_triage`
> (reusing `format_rows`), the exact zero-row / empty-filter / unknown-column /
> column-cap messages, and `render_summary` dispatching on the 15-column
> threshold (triage above, deep at/below; no focus tier). Test triage vs deep
> selection, the cap footer, the 1M-gate footer note, and each message's exact
> wording — no DB. Run pylint/pytest/mypy; one commit.
