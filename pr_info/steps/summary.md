# Issue #53 — `summarize_columns`: profile an arbitrary read-only SELECT

## Goal

Extend `summarize_columns` so the profiling **source** can be an arbitrary read-only
SELECT (`sql=`) instead of a persisted table (`schema=` + `table=`), without adding a
second tool. Everything downstream of the source — column narrowing, the 50-column cap,
the triage threshold, the scalar-aggregate pass, the value lists, the renderers — stays
exactly as it is today.

Contract after this change:

```python
summarize_columns(
    schema: str | None = None,
    table: str | None = None,
    sql: str | None = None,        # read-only SELECT; mutually exclusive with schema/table
    columns: list[str] | None = None,
    where: str | None = None,      # applied OUTSIDE the source (HAVING-like filtering)
    params: dict[str, Any] | None = None,
    n: int = 20,
    *, connection: str | None = None, database: str | None = None,
) -> str
```

---

## Architectural / design changes

### 1. New value object: `Source` (the central idea)

Today the pipeline threads `schema`, `table`, and `table_ref` separately, and `_run`
already carries 10 parameters. Rather than adding more, both paths converge on one frozen
dataclass built in the new `summarize/source.py`:

```python
@dataclass(frozen=True)
class Source:
    ref: exp.Table | exp.Subquery   # what every builder does .from_() on
    label: str | None               # "dbo.orders" for a table; None for a query
    metas: list[ColumnMeta]         # resolved column metadata
    notes: list[str]                # call-level footer lines
    types_probed: bool              # types came from a value probe, not a catalog
```

`_run` becomes source-agnostic and its parameter list *shrinks*. `label` is decision 16's
"source descriptor", carried in the same object rather than threaded separately.

```
before:  core ──► metadata_sql ──► ColumnMeta[] ──► _run(schema, table, table_ref, …)
after:   core ──► build_table_source(...)  ─┐
              └► build_query_source(...) ──┴──► Source ──► _run(source, …)
```

### 2. New module: `summarize/source.py` (source resolution)

`sql.py` is 651 lines and `tools.py` 402 — both near the repo's review threshold. Source
validation, `ORDER BY` handling, the value probe, type inference, and (step 6) the DMF
query form a coherent new concern and get their own module. Existing functions are **not**
moved: only new code lands there, so churn stays low.

### 3. New backend capability: `execute_readonly_query_with_columns`

`execute_readonly_query` returns `list[dict]` on both backends and discards
`cursor.description`; MSSQL's `dict(zip(columns, row))` silently collapses duplicate
column names. `get_isolated_connection` is not an alternative — on SQLite it yields the
*persistent* connection, which has no `PRAGMA query_only = ON`, so the Layer-2 read-only
backstop would be bypassed.

One new abstract method on `DatabaseBackend` returns rows **plus** ordered column names
under the same read-only guarantee. Its only consumer is the value probe; the T-SQL DMF
path keeps using `execute_readonly_query`, because the DMF's own result shape
(`name` / `column_ordinal` / `system_type_name`) has unique column names.

### 4. Shared leading-CTE gate moves down to `utils`

`count_tools` and `summarize` sit on the *same* line of `.importlinter`'s layer contract,
so they cannot import each other. `_has_leading_cte` and its rejection message move to
`utils/sql_placeholders.py`, where both tools reach them. The message is generalised by
one clause so it is accurate for both wrappers (both build a derived table).

### 5. Type resolution per backend, feeding the existing categoriser unchanged

The probe and the DMF both produce a **declared-type string**, never a category. That
keeps `categorize_type` and `_is_integer_type` (the T-SQL `CAST(… AS BIGINT)` SUM guard)
working untouched, and avoids a second source of truth for categories.

| Source | Names & ordinals | Types |
|---|---|---|
| Table (unchanged) | catalog | catalog `DATA_TYPE` / `pragma_table_info` |
| `sql`, T-SQL | `sys.dm_exec_describe_first_result_set` rows | `system_type_name` |
| `sql`, SQLite / T-SQL fallback | `cursor.description` via the new backend method | `type()` of the first non-`NULL` sampled value |

On SQLite the sample sees only `int` / `float` / `bytes` / `str` (the backend connects
without `detect_types`), so a DATE/DATETIME column resolves string and a BOOLEAN column
numeric — narrower than the table path's catalog types for the same column. That gap is
documented in step 3 and surfaced to the caller as `SQLITE_PROBE_TYPE_LIMITS_NOTE`, not
worked around.

### 6. Output marking without changing any renderer signature

`tools.py` already appends the `clamp_n` note *after* `render_summary` returns. Call-level
notes join that same trailing block, so `render_deep` / `render_summary` / `render_triage`
keep their current signatures and their ~20 existing test call sites are untouched. The
requirement — notes in a footer in both views — is met at the output level.

The per-column inline mark is one optional field, `ColumnMeta.note: str = ""` (3
construction sites repo-wide), rendered as
`notes  (unknown, string — type not determined: all sampled values were NULL)`.

### 7. Security

Unchanged gates, applied in this order to `sql`: `basic_preflight` → `read_only_violation`
→ **additional root allow-list** (`Select` / `Union` only; `read_only_violation` also
accepts `exp.Values`) → leading-CTE reject on T-SQL. Two user strings are never
concatenated: the `where` probe is built from the **re-rendered parsed** source, and the
DMF batch is literal-substituted by `substitute_named_with_literals` — the same helper and
the same deliberate trust decision as `MSSQLBackend.explain`.

### 8. What deliberately does not change

The table path's SQL, statistics, message wording, and exact catalog types; the triage
threshold and column cap; the `n` clamp; the value-list shapes; `table_not_found_message`
(no `sql`-path analogue); `server.py`; the config layer; `tach.toml` / `.importlinter`
(no new cross-layer edges).

---

## Files created / modified

### Created

| Path | Purpose |
|---|---|
| `src/mcp_tools_sql/summarize/source.py` | Source validation, `Source`, value probe, type inference, DMF |
| `tests/summarize/test_source.py` | Unit tests for the above |

### Modified

| Path | Change | Step |
|---|---|---|
| `src/mcp_tools_sql/backends/base.py` | New abstract `execute_readonly_query_with_columns` | 1 |
| `src/mcp_tools_sql/backends/sqlite.py` | Implementation on a fresh `query_only` connection | 1 |
| `src/mcp_tools_sql/backends/mssql.py` | Implementation via `cursor.description` | 1 |
| `src/mcp_tools_sql/utils/sql_placeholders.py` | `has_leading_cte` + `LEADING_CTE_REJECTION` | 2 |
| `src/mcp_tools_sql/count_tools.py` | Import the moved helper/message | 2 |
| `src/mcp_tools_sql/summarize/sql.py` | `SourceRef` alias, widened hints, `validate_where(table_ref, …)`, `ColumnMeta.note` | 3 |
| `src/mcp_tools_sql/summarize/render.py` | Inline type note; `empty_source_message` / `empty_filter_message` take a label | 3, 4 |
| `src/mcp_tools_sql/summarize/tools.py` | `validate_where` call site (3); `Source`-based `_run` + widened `try` (4); `sql` param, notes footer, description (5); `INVALID_SQL_EXC` import (6) | 3, 4, 5, 6 |
| `docs/architecture/architecture.md` | Backend-method row; `summarize` package row | 5 |
| `mcp-tools-sql.md` | Updated `summarize_columns` signature line (line ~216) | 5 |
| `tests/backends/test_sqlite.py`, `test_mssql.py`, `test_registry.py` | New method tests; `_FakeBackend` double | 1 |
| `tests/test_schema_tools_multitarget.py` | `_FanoutBackend` double | 1 |
| `tests/test_sql_placeholders.py`, `tests/test_count_tools.py` | Moved-helper tests; message assertion | 2 |
| `tests/summarize/test_sql.py` | `validate_where` call sites (~12, mechanical) | 3 |
| `tests/summarize/test_render.py` | Message tests; inline note test | 3, 4 |
| `tests/summarize/test_tools.py` | Empty-table text pin + backend-failure guards (4); end-to-end `sql=` tests (5, 6) | 4, 5, 6 |

---

## Steps

| # | Step | Depends on |
|---|---|---|
| 1 | [Backend read-only describe method](step_1.md) | — |
| 2 | [Move the leading-CTE gate to `utils`](step_2.md) | — |
| 3 | [`summarize/source.py`: validate + probe](step_3.md) | 1, 2 |
| 4 | [Refactor the table path onto `Source`](step_4.md) | 3 |
| 5 | [Wire the `sql=` parameter end to end](step_5.md) | 4 |
| 6 | [T-SQL DMF resolver with probe fallback](step_6.md) | 5 + prerequisite |

Each step is exactly one commit: tests + implementation + green checks.

**Step ordering is deliberate.** The value probe (step 3) is required on both backends
regardless — always on SQLite, as the fallback on T-SQL. Building it first means the
feature is complete and shippable after step 5, and the DMF in step 6 is a pure
enhancement. If the prerequisite below comes back "denied", step 6 is simply dropped with
no rework: probing on both backends is the design the issue itself names as honest in that
case.

---

## Prerequisite for step 6 only (decision 14)

Before starting step 6, connect as the documented read-only login
(`db_datareader` + `db_denydatawriter`) and run:

```sql
SELECT name, column_ordinal, system_type_name, is_hidden
FROM sys.dm_exec_describe_first_result_set(
    N'SELECT TOP 5 * FROM dbo.orders', NULL, 0);
```

Rows back → build step 6. Permission error → drop step 6; the probe note shipped in
step 5 is then simply the normal state, and decision 12's LOB hint (also shipped in
step 5) stops being a corner case. The `mssql_db` fixture cannot answer this — it uses a
schema-creating login.

---

## Design decisions taken while planning

| Decision | Choice | Why |
|---|---|---|
| Renderer signatures | Unchanged; notes appended in `tools.py` beside the clamp note | Same visible output, ~20 test call sites untouched |
| Probe output | Declared-type *strings*, not categories | `categorize_type` / `_is_integer_type` keep working with zero changes |
| Inline unknown-type mark | One optional `ColumnMeta.note` field | 3 construction sites; no parallel structure |
| `validate_where` | Takes the built `table_ref` instead of `schema`/`table` (option A) | Removes a duplicated `build_table_ref` call; ~12 mechanical test edits |
| `build_table_ref` / `validate_where` | Stay in `sql.py` | 750 is the enforced limit; moving them is cosmetic churn |
| Shared CTE message | Generalised by one clause, `count_records`' test updated | Accurate for both wrappers; both build a derived table |
| Source/`schema`+`table` conflict | One constant for both "both" and "neither" | One string, one-turn recovery |
| LOB failure hint | Appended at the existing `except` tail in `core` | No new try/except, no error-code sniffing |
| Zero-row source | Resolution stays before the count | Resolution is what rejects a bad source (deliberate, per the issue) |
| Source build inside `core`'s `try` | Widen the existing tail to open before `build_table_source` / `build_query_source` | Both execute a backend query (metadata / probe / DMF); the metadata query is inside the `try` today, and an unresolvable `sql` source has no `table_not_found` analogue — the backend error *is* the report |
| SQLite temporal / boolean probe gap | Document and emit `SQLITE_PROBE_TYPE_LIMITS_NOTE` on `sqlite`; do not recover the declared type | `sqlite3` connects without `detect_types`, so DATE/BOOLEAN arrive as `str`/`int`; `PARSE_DECLTYPES` covers only two types and *raises* on malformed data. Same class of gap the issue already defers for SQLite views — but marked, not silent |
| `Source.label` on SQLite | `schema.table`, not bare `table` | The status messages print the schema on both dialects today; `build_table_ref`'s decision-20 rule is about SQL, not message text |
| Test fixtures | Reuse `profiling_db`; self-join `profile_me` | No new fixture for the join / duplicate-name cases |

---

## Open verification points

1. **SQLite duplicate-column names.** The issue reports `cursor.description` yielding
   `['id', 'name', 'id:1', 'city']`. Step 1 pins the *actual* behaviour with a test before
   step 3 keys a rejection rule on it. If the observed form differs, step 3's rule follows
   the test, not this document.
2. **DMF through the parameter binder.** The DMF batch is passed as a bound `nvarchar`
   argument, so it round-trips `translate_named_to_qmark`. Step 6 asserts the rendered SQL
   in a MagicMock test before any live run.

---

## Quality gates (every step)

`mcp__tools-py__run_pylint_check`, `mcp__tools-py__run_pytest_check`, and
`mcp__tools-py__run_mypy_check` must all pass, plus CI's ruff (Google docstrings with
`Args:` / `Returns:` on `src`), black, isort, `lint-imports`, `tach check`, `vulture`
(scans `src` *and* `tests`, so test-only usage counts), and the 750-line file-size check.
Run `./tools/format_all.sh` before committing.
