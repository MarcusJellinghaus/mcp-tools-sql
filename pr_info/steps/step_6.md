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
DISTINCT_GATE_ROWS: int = 1_000_000   # triage omits distinct above this row count

def render_triage(profiles: list[ColumnProfile], total_columns: int,
                  distinct_gated: bool) -> str: ...

def render_summary(profiles: list[ColumnProfile], total_columns: int,
                   n: int, distinct_gated: bool) -> str: ...
    # dispatch: len(profiles) > 15 -> triage else deep

def empty_table_message(schema: str, table: str) -> str: ...
def table_not_found_message(schema: str, table: str) -> str: ...
def empty_filter_message(total_rows: int) -> str: ...
def unknown_columns_message(bad: list[str], available: list[str]) -> str: ...
def empty_columns_message(available: list[str]) -> str: ...
def column_cap_footer(shown: int, total: int) -> str: ...

NO_COLUMNS_TEXT: str = "No columns to profile."   # render_summary defensive guard
```

## HOW

- `render_triage`: one row per column via `format_rows` (import from
  `mcp_tools_sql.formatting`) with keys
  `{name, type, null_pct, distinct, min, max}`. `distinct` shows `—` (or the
  gate note) when `distinct_gated`. **A `None` `ColumnProfile.distinct` also
  renders `—`, regardless of the gate** — the same blank convention as an
  absent min/max. This is not only the gated case: step 3 never emits
  `COUNT(DISTINCT)` for `other`/binary columns (LOB cannot be counted
  distinctly), so those columns carry `distinct is None` even in an *ungated*
  triage. Read it through the same blanking helper used for min/max; never let
  the literal string `None` reach `format_rows`/tabulate.
  **`min`/`max` are the value min/max, which
  the scalar pass (step 3) computes for numeric, temporal, and string columns;
  boolean and other/LOB columns show `—`** (read `stats.get("min")` /
  `stats.get("max")`, blanking the marker when absent).
  **The boolean/other exclusion is a hard SQL constraint, not a discretionary
  reduction:** T-SQL rejects `MIN`/`MAX` on `bit` (boolean) and on the LOB
  types (`text`/`ntext`/`image`, classified as other), so those aggregates
  cannot legally appear in the scalar pass at all. Every column type where value
  min/max is legal — numeric, temporal, string — populates the triage line as
  the issue's contract requires; the two excluded categories are blank because
  the database forbids the aggregate, so the triage line matches the issue for
  every column it can. Append `column_cap_footer` when
  `total_columns > len(profiles)`, plus a footer hint that a narrowed `columns=`
  call yields the deep block. When gated, state the `DISTINCT_GATE_ROWS`
  (1M-row) reason in the footer.
- `render_summary`: `render_triage` when `len(profiles) > TRIAGE_THRESHOLD`,
  else `render_deep(profiles, n)`. A 1-column call renders the same deep block
  as one of 10 (no focus tier).
- Messages (exact wording from the issue):
  - empty table → `Table {schema}.{table} is empty (0 rows). Use read_columns
    for its column definitions.`
  - table not found → `Table {schema}.{table} not found (no such table or no
    columns). Check the schema and table name.` (emitted when the metadata query
    returns zero rows — the table does not exist, distinct from an existing but
    empty table)
  - empty filter → `No rows match the where predicate (table has {N} rows).`
  - unknown columns → `Unknown column(s): {bad}. Available: {available…}` (echo
    declared casing).
  - empty `columns` list → `No columns selected: columns= was an empty list.
    Available: {available…}` — same error class and shape as the unknown-column
    message (echo declared casing). Returned by step 7 *before* any data query.
  - column cap → `Showing 50 of {N} columns. Use columns= to select others.`

## ALGORITHM (`render_summary`)

```
if not profiles: return NO_COLUMNS_TEXT   # defensive guard, see below
if len(profiles) > TRIAGE_THRESHOLD: return render_triage(profiles, total_columns, distinct_gated)
return render_deep(profiles, n)
```

The empty branch is a **defensive guard, not a reachable path**: step 7 rejects
an explicitly empty `columns=[]` with `empty_columns_message` before any data
query, short-circuits zero rows with the empty-table / empty-filter messages,
and a table that exists always has ≥ 1 column. It returns the fixed
`NO_COLUMNS_TEXT` constant so an unexpected empty list yields a sentence rather
than an empty string or a crash.

## DATA

All functions return `str`.

## TESTS

- 16 profiles → triage (one line each, no value lists); 15 → deep blocks.
- triage with `total_columns=412, len=50` → cap footer
  `Showing 50 of 412 columns.`; with `distinct_gated=True` → gate reason in
  footer and `distinct` column shows the gated marker.
- each message renders the exact wording; `unknown_columns_message` echoes
  declared casing and lists availables; `empty_columns_message` renders its own
  wording and lists availables; `table_not_found_message` and
  `empty_table_message` render distinct text (not-found vs empty).
- triage with numeric/temporal/string columns → each shows its value
  `min`/`max`; a boolean/other column whose `stats` has no `min`/`max` → those
  cells render `—`.
- **ungated** triage (`distinct_gated=False`) containing an `other`/binary
  column whose `distinct is None` → that cell renders `—`; assert the literal
  `"None"` appears nowhere in the rendered table.
- `render_summary([], …)` → `NO_COLUMNS_TEXT` (defensive guard, non-empty
  sentence).
- 1-column list → deep block (not a special tier).

## COMMIT

`feat(summarize): add triage renderer, messages and view dispatch`

## PROMPT

> Implement Step 6 from `pr_info/steps/step_6.md` (context in
> `pr_info/steps/summary.md`). Extend `summarize/render.py` with `render_triage`
> (reusing `format_rows`), the exact zero-row / empty-filter / unknown-column /
> empty-column-list / column-cap messages, and `render_summary` dispatching on
> the 15-column threshold (triage above, deep at/below; no focus tier). Blank a
> `None` `distinct` to `—` (gated *and* `other`/LOB columns) so tabulate never
> prints `None`. Test triage vs deep selection, the cap footer, the
> `DISTINCT_GATE_ROWS` footer note, the `None`-distinct blanking, and each
> message's exact wording — no DB. Run pylint/pytest/mypy; one commit.
