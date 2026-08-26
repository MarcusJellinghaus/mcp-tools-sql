# Step 6 — T-SQL: `sys.dm_exec_describe_first_result_set` with probe fallback

**Goal:** on SQL Server, resolve the source's column names, ordinals, and *exact* types
from the DMF instead of a value sample — without executing the query. Falls back to step
3's probe, never silently.

**Depends on:** step 5 **and** the prerequisite below.

---

## ⚠ Prerequisite — run before writing any code

Connect as the documented read-only login (`db_datareader` + `db_denydatawriter`) and run:

```sql
SELECT name, column_ordinal, system_type_name, is_hidden
FROM sys.dm_exec_describe_first_result_set(
    N'SELECT TOP 5 * FROM dbo.orders', NULL, 0);
```

- **Rows back** → build this step.
- **Permission error** → **drop this step entirely.** The probe shipped in step 5 already
  works on both backends and already prints the types-probed note, which is the design the
  issue calls honest in that case. Record the outcome in the issue and close it after
  step 5.

The `mssql_db` fixture cannot answer this — it uses a schema-creating login, so a green
integration test there proves nothing about the shipping permission model.

---

## WHERE

| File | Change |
|---|---|
| `src/mcp_tools_sql/summarize/source.py` | `describe_columns` (DMF) + dispatch inside `build_query_source`; **owns `INVALID_SQL_EXC`** (moved from `tools.py`) |
| `src/mcp_tools_sql/summarize/tools.py` | Imports `INVALID_SQL_EXC` from `summarize.source`; drops its local `_PYODBC_ERROR` / `_INVALID_SQL_EXC` definitions |
| `tests/summarize/test_source.py` | DMF SQL shape, parsing, fallback |
| `tests/summarize/test_tools.py` | One T-SQL end-to-end-shaped MagicMock test |
| `tests/backends/test_mssql.py` | Optional `mssql_integration` test against a live server |

## WHAT

```python
# summarize/source.py
DMF_SQL: str = (
    "SELECT name, column_ordinal, system_type_name "
    "FROM sys.dm_exec_describe_first_result_set(:src, NULL, 0) "
    "WHERE is_hidden = 0 ORDER BY column_ordinal"
)
DMF_FALLBACK_NOTE: str   # names the reason; printed alongside TYPES_PROBED_NOTE

# Moved here from tools.py — see HOW. Public, because tools.py now imports it.
INVALID_SQL_EXC: tuple[type[BaseException], ...] = (sqlite3.Error, *_PYODBC_ERROR)

def describe_columns(
    backend: DatabaseBackend, ref: exp.Subquery, params: dict[str, Any] | None
) -> tuple[list[ColumnMeta] | None, str | None]: ...
```

## HOW

- **Move the exception tuple first.** The fallback dispatch has to catch the same
  `sqlite3.Error` / `pyodbc.Error` family that `core` catches, but that tuple is
  `_INVALID_SQL_EXC` in `summarize/tools.py` (line ~61) and `source.py` cannot import it:
  `tools.py` already imports `source.py` (steps 4–5), so the reverse edge is a cycle. Move
  the `try: import pyodbc` block, `_PYODBC_ERROR`, and the tuple into `source.py` as the
  public `INVALID_SQL_EXC`, delete them from `tools.py`, and have `tools.py` import
  `INVALID_SQL_EXC` from `mcp_tools_sql.summarize.source` alongside `Source`,
  `build_query_source`, and `build_table_source`. Verbatim move — no logic change — and
  `core`'s `except` clause just renames. No new layer edges: both modules are in
  `summarize`.
- The batch is passed as a **bound** `nvarchar` argument (`:src`), so nothing is
  concatenated into the DMF call. Its *contents* are produced by
  `substitute_named_with_literals(ref.this.sql(dialect="tsql"), params or {}, "tsql")` —
  the same helper and the same deliberate trust decision as `MSSQLBackend.explain`, and
  safe because the source has already passed the read-only gate and been re-rendered by
  sqlglot. The DMF errors on a batch with undeclared parameters, which is why literals are
  required here.
- Runs through the existing `execute_readonly_query` — the DMF's result shape has unique
  column names, so the step-1 method is not needed here.
- `system_type_name` carries precision suffixes (`nvarchar(50)`, `decimal(10,2)`) where the
  table path's `INFORMATION_SCHEMA.DATA_TYPE` gives the bare type. `categorize_type` and
  `_is_integer_type` are substring-based so both work — but nothing downstream may
  introduce an exact type comparison.
- The same column-name rejection from step 3 applies to DMF rows (`name` can be `NULL` for
  an unnamed expression); reuse the one helper.
- `build_query_source` dispatch: `tsql` → `describe_columns`, and on **any** failure
  (`INVALID_SQL_EXC`, or an empty result set) fall back to `probe_columns` with
  `DMF_FALLBACK_NOTE` added. `sqlite` → `probe_columns` unchanged. `types_probed` is
  `False` only when the DMF succeeded — so the LOB hint and the types-probed note both
  follow the actual resolver used.

## ALGORITHM

```
describe_columns(backend, ref, params):
    batch = substitute_named_with_literals(ref.this.sql(dialect="tsql"), params or {}, "tsql")
    rows = backend.execute_readonly_query(DMF_SQL, {"src": batch})
    if not rows: return (None, "empty describe result")
    bad = _name_rejection([r["name"] for r in rows]);  if bad: return (None, bad)
    metas = [ColumnMeta(r["name"], r["system_type_name"],
                        categorize_type(r["system_type_name"], "tsql"), r["column_ordinal"])
             for r in rows]
    return (metas, None)
```

## DATA

Same `(metas, error)` shape as `probe_columns`, so the dispatch is a two-branch try/fallback
and `Source` is unaffected. DMF ordinals are 1-based, the probe's are 0-based — ordinals are
used only for sorting and the 50-column cap, so the base is irrelevant within a call.

## TESTS (write first)

1. `describe_columns` renders `DMF_SQL` with the batch bound as `:src`; assert the exact
   SQL string and the params dict handed to the backend (MagicMock).
2. The bound batch has `:name` placeholders replaced by literals, with a string value
   correctly escaped (`O'Brien` → `'O''Brien'`).
3. **Binder round-trip:** `translate_named_to_qmark(DMF_SQL, "tsql")` yields one `?` for
   `:src` and leaves `sys.dm_exec_describe_first_result_set(...)`, `is_hidden = 0`, and the
   `ORDER BY` intact. This is verification point 2 from the summary — if sqlglot mangles the
   table-valued function, adjust `DMF_SQL` (and only `DMF_SQL`) until it round-trips.
4. DMF rows → `ColumnMeta` with `system_type_name` verbatim, including precision suffixes;
   `nvarchar(50)` → string, `bigint` → numeric with `_is_integer_type` true, `bit` →
   boolean, `text` → other, `timestamp` → other.
5. A DMF error (pyodbc-style exception) falls back to `probe_columns`, and the returned
   `Source.notes` contain **both** the fallback note and the types-probed note;
   `types_probed is True`.
6. DMF success → neither note, `types_probed is False`.
7. `is_hidden` filtering and `column_ordinal` ordering are expressed in the SQL (covered by
   test 1's exact-string assertion).
8. Optional `mssql_integration` test: `describe_columns` against a live server returns the
   real column list for a join over the `mssql_db` fixture's tables.

## ACCEPTANCE

T-SQL `sql=` calls report catalog-grade types with no footer note; a DMF failure degrades to
the probe with both notes shown; SQLite is untouched; all three MCP checks green.

## LLM PROMPT

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_6.md`.
>
> **First confirm the prerequisite at the top of the step file has been run and returned
> rows.** If it returned a permission error, stop and report — this step is dropped by
> design, not worked around.
>
> Then implement step 6 only, test-first. Start by moving `_INVALID_SQL_EXC` (and its
> `pyodbc` import guard) from `summarize/tools.py` into `summarize/source.py` as the public
> `INVALID_SQL_EXC`, re-pointing `tools.py` at it — `source.py` cannot import `tools.py`,
> which already imports `source.py`. Then add `describe_columns` and the
> `DMF_SQL` / `DMF_FALLBACK_NOTE` constants to `src/mcp_tools_sql/summarize/source.py`, and
> make `build_query_source` prefer the DMF on `tsql` with a fallback to `probe_columns`
> that records both notes. Do not change the SQLite path.
>
> Write test 3 (the `translate_named_to_qmark` round-trip) early — it determines the exact
> `DMF_SQL` text.
>
> Use MCP tools for all file and check operations. When done, run
> `mcp__tools-py__run_pylint_check`, `mcp__tools-py__run_pytest_check`
> (`extra_args=["-n", "auto"]`), and `mcp__tools-py__run_mypy_check`, and fix everything
> they report.
