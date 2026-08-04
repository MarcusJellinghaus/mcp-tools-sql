# Feature: `summarize_columns` — per-column data profiling tool

Implements issue #43. Adds a programmatic MCP builtin, `summarize_columns`, that
profiles the **data** in a table's columns (counts, nulls, category-appropriate
statistics, duplication-driven value lists) and renders an LLM-friendly text
block. It follows the `count_records` template
(`src/mcp_tools_sql/count_tools.py`): a `build_tool_fn`-assembled tool that
resolves its target per call via `build_target_params(targets, star=False)`
(pinned — no `"*"` fan-out), executes through `backend.execute_readonly_query`,
and returns a plain string.

Read the issue for the full behavioural contract. This summary records the
**design decisions** that shape the code and the **module layout** the steps
build against.

---

## Tool contract

```python
summarize_columns(
    schema: str,
    table: str,
    columns: list[str] | None = None,   # narrow to specific columns
    where: str | None = None,           # optional predicate, :name placeholders
    params: dict[str, Any] | None = None,
    n: int = 20,                        # value-list length, hard clamp 50
    *, connection: str | None = None, database: str | None = None,
) -> str
```

Registered by adding `"summarize_columns"` to `PROGRAMMATIC_BUILTIN_TOOLS` in
`schema_tools.py` and wiring `SummarizeTools(...).register(mcp)` into
`server.py`.

---

## Architectural / design changes

### 1. New package `mcp_tools_sql.summarize` (not a flat module, not four files)

The tool is materially larger than `count_records` (metadata query, five type
categories, dialect-specific SQL generation, two renderers). A **single flat
module would risk the 750-line file limit**; a package of focused files keeps
each file small **and** presents the whole tool as *one* architectural unit —
so `tach.toml` and `.importlinter` gain exactly **one** module/layer entry, not
three. This is the KISS balance: minimal boundary surface, focused files. A
third internal file can be added later with zero boundary churn.

```
src/mcp_tools_sql/summarize/
    __init__.py     # exports SummarizeTools
    sql.py          # type categoriser + all sqlglot SQL generation + data types
    render.py       # deep-view + triage renderers + messages
    tools.py        # SummarizeTools: signature, orchestration, registration
```

Dependency position mirrors `count_tools` (tool_implementation layer). The
package depends on `backends`, `formatting`, `tool_logging`, `query_helpers`
(for `build_target_params`), `tool_builder`, and `utils` (for
`sql_placeholders`). Unlike `count_tools`, it **does** depend on `formatting`
(triage reuses `format_rows`).

### 2. Type categoriser lives *in the package*, not in `utils/data_type_utility/`

The issue warns only against extending `type_mapping.py` (which maps *config*
type strings to Python types — a different concern). It does **not** require a
new `utils` module. A ~40-line prefix/affinity classifier
(`categorize_type`) lives next to its only caller in `summarize/sql.py`
(YAGNI — promote to `utils` only if a second caller appears).

### 3. Reuse, don't re-implement

- `where` validation reuses `basic_preflight` (unbound-placeholder / multi-
  statement / parse checks) **unchanged**, then `read_only_violation`, then the
  predicate is re-rendered from the AST — the exact fail-closed pattern
  `count_records` uses.
- All executable SQL is built as a sqlglot AST and rendered with
  `.sql(dialect=...)`; dialect differences (`TOP n`/`LIMIT n`, quoting,
  `LEN`/`LENGTH`) fall out of the renderer. **Never string-concatenate dialect
  SQL.** Where sqlglot already translates a function across dialects (e.g.
  `exp.Length`), the neutral node is built once; only genuinely divergent
  semantics are hand-branched (`SUM(CAST … BIGINT)` on T-SQL integers,
  `DATALENGTH`, the LOB `GROUP BY` exclusion).
- Identifiers are quoted via `exp.to_identifier(name, quoted=True)` — **not**
  the `identifiers.py` regex whitelist (which would reject `Order Details`).
- Triage output reuses `format_rows` (its `Showing N of M` footer convention).

### 4. Static metadata SQL, AST'd data SQL

The metadata query (`INFORMATION_SCHEMA.COLUMNS` / `pragma_table_info`) injects
only **bound values** (`:schema`, `:table`), so it is a per-dialect constant
string — no AST needed. Every *data* query injects **identifiers** (table,
columns) which cannot be bound, so those are AST-built and rendered.

### 5. Roadmap update

`mcp-tools-sql.md` Phase 3 (`read_table_profile`) is renamed to
`summarize_columns`; the duplication-driven value list subsumes
`read_distinct_values`.

---

## Execution pipeline (built across steps 2–7)

Order matters — the metadata query carries no `where`/`params`.

1. **Metadata** — column names, declared types, ordinal (step 2).
2. **Validate / narrow** `columns` case-insensitively against metadata; echo
   declared casing; unknown names fail the whole call (step 7).
3. **`COUNT(*)`** with `where` applied. Short-circuits on zero rows; feeds the
   1M distinct gate (steps 2, 7).
4. **Scalar-aggregate pass** — every statistic for every profiled column in one
   `SELECT`, one table scan (step 3).
5. **Per-column value lists** — one `GROUP BY` per profiled column, deep view
   only (step 4).

Two-tier view by profiled-column count (after narrowing, after the 50-column
cap): **> 15 → triage** (one `format_rows` line per column, no value lists,
distinct omitted above 1M rows); **≤ 15 → deep** (full labelled block per
column, value lists never suppressed). `n` is the only depth knob.

---

## Shared data structures (defined once, consumed across steps)

Defined in `summarize/sql.py` (data layer) unless noted:

```python
Category = Literal["numeric", "temporal", "string", "boolean", "other"]

@dataclass(frozen=True)
class ColumnMeta:
    name: str          # declared casing, echoed in output
    declared_type: str # raw type string from metadata
    category: Category
    ordinal: int       # for the 50-column cap + triage ordering

@dataclass(frozen=True)
class ColumnProfile:          # defined in render.py; built in tools.py
    meta: ColumnMeta
    rows: int                 # filtered COUNT(*)  (same for all columns)
    non_null: int
    distinct: int | None      # None when gated out of triage
    stats: dict[str, Any]     # category-specific: min/max/mean/len_avg/…
    values: list[tuple[Any, int]] | None  # (value, freq) top OR (value,) sample
    value_kind: Literal["top", "sample", "none"]
```

Scalar-pass aggregates are aliased `c{idx}__{stat}` (e.g. `c0__nonnull`,
`c0__distinct`, `c0__min`) so one result row maps back per column.

---

## Type categories & statistics

| Category | Statistics (in the scalar pass) | Value list? |
|---|---|---|
| numeric | non_null, nulls, distinct, min, max, mean `AVG(CAST … FLOAT)`, sum `SUM(CAST … BIGINT)` on T-SQL ints else `SUM(CAST … FLOAT)`, zero count, negative count | yes |
| temporal | non_null, nulls, distinct, min, max | yes |
| string | non_null, nulls, distinct, empty `LTRIM(RTRIM(c))=''`, len min/max/avg via `LEN`/`LENGTH` (characters) | yes |
| boolean | true / false / null counts, true % | yes |
| other/binary | non_null, nulls; size in bytes via `DATALENGTH` (T-SQL only) | **no** — LOB types (`text`/`ntext`/`image`) cannot appear in `GROUP BY`/`DISTINCT`/comparisons, so this category has no distinct and no value list |

---

## Determinism, cost & safety invariants (must hold, tested)

- Value-list ordering is **total**: `ORDER BY COUNT(*) DESC, value ASC`.
- 50-column cap by ordinal (footer: `Showing 50 of N columns. Use columns= to
  select others.`); keeps the scalar pass under T-SQL's 4,096-expression limit.
- `n` clamps to 50 (default 20), noted in `_cap_max_rows` style.
- 1M-row distinct gate applies to **triage only**; deep view is always exact
  (stated, un-gated, by design).
- `NULL` ranks as an ordinary row in the top-values list **and** keeps its
  separate null count; remainder line is pure arithmetic (no extra query).
- Display-truncate list values at 60 chars + `…`; counts stay exact.
- Zero rows: short-circuit after `COUNT(*)`; distinct wording for empty table
  vs empty filter.

---

## Test strategy (issue decision #14)

- **Rendered-SQL string assertions per dialect** (sqlite + tsql via `MagicMock`)
  for every SQL builder — casts, `LEN`/`DATALENGTH`, `TOP n`/`LIMIT n`, LOB
  exclusion, total ordering.
- **SQLite end-to-end** through `create_connected_server_and_client_session`
  for the full pipeline, both views, all categories, and every message.
- Renderers tested against hand-built `ColumnProfile` values (no DB).
- **No live SQL Server** (accepted risk; T-SQL ships unverified).

---

## Files created / modified

**Created**

- `src/mcp_tools_sql/summarize/__init__.py`
- `src/mcp_tools_sql/summarize/sql.py`
- `src/mcp_tools_sql/summarize/render.py`
- `src/mcp_tools_sql/summarize/tools.py`
- `tests/summarize/__init__.py`
- `tests/summarize/conftest.py`  (profiling fixture: temporal/boolean/duplicate/unique columns)
- `tests/summarize/test_sql.py`
- `tests/summarize/test_render.py`
- `tests/summarize/test_tools.py`

**Modified**

- `src/mcp_tools_sql/schema_tools.py`  — add `"summarize_columns"` to `PROGRAMMATIC_BUILTIN_TOOLS`
- `src/mcp_tools_sql/server.py`  — register `SummarizeTools`
- `tach.toml`  — add `mcp_tools_sql.summarize` module + layer position
- `.importlinter`  — add `mcp_tools_sql.summarize` to the tool layer
- `mcp-tools-sql.md`  — roadmap: `read_table_profile` → `summarize_columns`

---

## Steps (one commit each, TDD)

1. Type categoriser + package skeleton.
2. `where` validation, table ref, metadata SQL, `COUNT(*)` SQL.
3. Scalar-aggregate pass SQL (per category) + `ColumnMeta`.
4. Value-list SQL (top-values + sample-values).
5. Deep-view renderer + `ColumnProfile`.
6. Triage renderer + messages + view dispatch.
7. `SummarizeTools` orchestration + registration + wiring + roadmap.
