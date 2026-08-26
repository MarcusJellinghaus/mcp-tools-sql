# Step 3 — `summarize/source.py`: validate a SELECT source and probe its columns

**Goal:** the two pure-ish building blocks of the `sql` path — turn a user SELECT into a
validated, aliased derived-table reference, and resolve its output columns from a few-row
value probe. No tool wiring yet; nothing user-visible changes.

**Depends on:** steps 1, 2. **Blocks:** step 4.

---

## WHERE

| File | Change |
|---|---|
| `src/mcp_tools_sql/summarize/source.py` | **New.** `validate_source`, `probe_columns`, notes constants |
| `src/mcp_tools_sql/summarize/sql.py` | `SourceRef` alias, widened `table_ref` hints, `validate_where(where, table_ref, params, dialect)`, `ColumnMeta.note` |
| `src/mcp_tools_sql/summarize/render.py` | Render the inline type note in the column header |
| `src/mcp_tools_sql/summarize/tools.py` | **Call site only.** `core` builds `table_ref` before `validate_where` and passes it (line ~258); import list at line ~49 unchanged (`build_table_ref` is still used) |
| `tests/summarize/test_source.py` | **New.** |
| `tests/summarize/test_sql.py` | ~12 mechanical `validate_where` call-site updates |
| `tests/summarize/test_render.py` | One inline-note test |

## WHAT

```python
# summarize/sql.py
SourceRef = exp.Table | exp.Subquery          # module-level alias, used in all hints

@dataclass(frozen=True)
class ColumnMeta:
    name: str
    declared_type: str
    category: Category
    ordinal: int
    note: str = ""                            # NEW: inline mark, "" for the normal case

def validate_where(                            # signature change: schema/table -> table_ref
    where: str | None,
    table_ref: SourceRef,
    params: dict[str, Any] | None,
    dialect: str,
) -> tuple[exp.Expression | None, str | None]: ...

# build_count_sql / build_scalar_sql / build_value_list_sql: table_ref: SourceRef
```

```python
# summarize/source.py
PROBE_ROWS: int = 5
ORDER_BY_STRIPPED_NOTE: str
ROW_LIMITED_NOTE: str
TYPES_PROBED_NOTE: str

def validate_source(
    sql: str, params: dict[str, Any] | None, dialect: str
) -> tuple[exp.Subquery | None, list[str], str | None]: ...

def probe_columns(
    backend: DatabaseBackend, ref: exp.Subquery, params: dict[str, Any] | None, dialect: str
) -> tuple[list[ColumnMeta] | None, str | None]: ...
```

## HOW

- `source.py` imports `basic_preflight`, `read_only_violation`, `has_leading_cte`,
  `LEADING_CTE_REJECTION` from `utils.sql_placeholders`, and `ColumnMeta`,
  `categorize_type` from `summarize.sql`. It imports `DatabaseBackend` for typing only
  (`TYPE_CHECKING`), matching `tools.py`. No new `tach.toml` / `.importlinter` edges.
- `validate_where` no longer calls `build_table_ref` itself — the caller passes the ref it
  already built. Its **only** production caller is `summarize/tools.py`'s `core`, which
  today calls `validate_where(where, schema, table, params, dialect)` at line ~258 and
  builds `table_ref` at line ~263. Swap those two lines so the ref is built first and
  passed in:

  ```python
  table_ref = build_table_ref(schema, table, dialect)
  predicate, where_error = validate_where(where, table_ref, params, dialect)
  ```

  That one call site **must** change in this same commit or mypy and pytest fail; it is the
  only edit `tools.py` receives in step 3 (no `Source`, no `sql` param — those are steps 4
  and 5). The import block at line ~49 is unchanged: `build_table_ref` and `validate_where`
  are both still imported.
- The probe becomes
  `f"SELECT 1 FROM {table_ref.sql(dialect=dialect)} WHERE {where}"`. For a `Subquery` ref
  that renders the **re-rendered parsed** source, never the raw user text.
- `render.py` column header becomes
  `f"{meta.name}  ({meta.declared_type}, {meta.category}{f' — {meta.note}' if meta.note else ''})"`.
  The triage type cell is unchanged (it shows `unknown`).
- Probe SQL is built from the ref, not by string concatenation:
  `exp.select(exp.Star()).from_(ref.copy()).limit(PROBE_ROWS).sql(dialect=dialect)`.
- `params` is passed through to the probe so `:name` placeholders *inside* the source bind.

## ALGORITHM

```
validate_source(sql, params, dialect):
    verdict = basic_preflight(sql, params, dialect) or read_only_violation(sql, dialect)
    if verdict: return (None, [], verdict)
    parsed = sqlglot.parse_one(sql, read=dialect)
    if not isinstance(parsed, (exp.Select, exp.Union)): return (None, [], ROOT_REJECTION)
    if dialect == "tsql" and has_leading_cte(sql, dialect): return (None, [], LEADING_CTE_REJECTION)
    row_limited = bool(parsed.args.get("limit") or parsed.args.get("offset"))
    if not row_limited and parsed.args.get("order"):
        parsed.set("order", None); notes.append(ORDER_BY_STRIPPED_NOTE)
    if row_limited: notes.append(ROW_LIMITED_NOTE)
    return (exp.Subquery(this=parsed, alias=exp.TableAlias(this=exp.to_identifier("src"))), notes, None)

probe_columns(backend, ref, params, dialect):
    names, rows = backend.execute_readonly_query_with_columns(probe_sql, params)
    bad = _name_rejection(names);  if bad: return (None, bad)
    for idx, name in enumerate(names):
        value = first non-None in (row[idx] for row in rows)          # None if all NULL/no rows
        decl = _declared_type_for(value, dialect) if value is not None else "unknown"
        meta = ColumnMeta(name, decl, categorize_type(decl, dialect), idx, note="")
        if value is None: meta = replace(meta, category="string", note=UNKNOWN_TYPE_NOTE)
    return (metas, None)
```

`TOP` (T-SQL), `LIMIT` (SQLite) and `OFFSET … FETCH` all land in `args["limit"]`, so the
one test covers all three. The `ORDER BY` strip is conditional on purpose: with a row limit
the clause decides *which* rows get profiled, so stripping it would silently change the
answer.

### Python value → declared type (probe only)

`_declared_type_for(value, dialect)` takes the dialect: the last row below is
dialect-dependent, because `categorize_type` is.

| Value type | Declared type | Category via `categorize_type` |
|---|---|---|
| `bool` | `"bit"` | boolean (pyodbc only; `sqlite3` yields `int` for booleans — documented, accepted) |
| `int` | `"INTEGER"` | numeric (and `_is_integer_type` → `True`, keeping the T-SQL BIGINT SUM guard) |
| `float` | `"REAL"` | numeric |
| `Decimal` | `"decimal"` | numeric |
| `datetime` | `"datetime"` | temporal — **not** `"timestamp"`, which T-SQL maps to `other` (rowversion) |
| `date` | `"date"` | temporal |
| `bytes` / `bytearray` | `"BLOB"` | other |
| anything else | `"TEXT"` on `sqlite`, `"nvarchar"` on `tsql` | string on both |

Order matters: `bool` before `int`, `datetime` before `date`.

**The `str` row must not be `"TEXT"` on T-SQL.** `categorize_type` guards
`text`/`ntext`/`image` as `other` on `tsql` (the LOB guard in `sql.py`), so a probed
`"TEXT"` would categorise **every** string column as `other` — no distinct, no length
stats, no value list — on exactly the path where the probe is the only resolver (step 5
until step 6 lands, and permanently if step 6's prerequisite comes back denied).
`"nvarchar"` contains the `char` token, so it categorises as `string` on both dialects.
`"TEXT"` is kept on `sqlite` so the rendered `declared_type` matches what the table path
already prints there (`(TEXT, string)`).

### Column-name rejection

Reject when any name is empty/`None`, when names collide case-insensitively, or when a
name contains `":"` (SQLite's duplicate disambiguation, as pinned by step 1 test 5 —
follow that test if the observed form differs). Message names the recovery:

> `The source query has duplicate or unnamed output columns: id. Alias each output column (e.g. SELECT a.id AS a_id, b.id AS b_id) so every name is unique.`

## DATA

- `validate_source` → `(ref, notes, error)`; exactly one of `ref` / `error` is set. `notes`
  are plain footer sentences, in the order they should print.
- `probe_columns` → `(metas, error)`; `metas` ordered by output ordinal (0-based; ordinals
  are only used for sorting and the 50-column cap, so the base does not matter).

## TESTS (write first)

`tests/summarize/test_source.py` — `validate_source`
1. Plain SELECT → aliased `AS src` subquery renders correctly on both dialects.
2. `INSERT` / `DROP` / `SELECT … INTO` rejected (gates reused).
3. `VALUES (1),(2)` rejected by the root allow-list although `read_only_violation` allows it.
4. Multi-statement, empty, unparseable, unbound `:name` → the `basic_preflight` verdicts.
5. Leading `WITH` rejected on `tsql` with `LEADING_CTE_REJECTION`; **accepted** on `sqlite`.
6. `ORDER BY` without a limit → stripped, note present, rendered SQL has no `ORDER BY`.
7. `SELECT TOP 10 … ORDER BY total DESC` (tsql) and `… LIMIT 10` (sqlite) → `ORDER BY`
   **kept**, no strip note, row-limited note present.
8. `:name` placeholders inside the source survive into the rendered ref.

`probe_columns` (MagicMock backend returning canned `(names, rows)`)
9. Mixed types map to the table above; ordinals ascend. Parameterise over both dialects
   so the `str` row is asserted on each.
9b. **T-SQL string regression guard.** A probed `str` value under `dialect="tsql"` yields
    `declared_type == "nvarchar"` and `category == "string"` — **not** `"other"`. Assert the
    category directly, then assert the consequence: `build_scalar_sql` for that
    `ColumnMeta` emits the string aggregates (`COUNT(DISTINCT)`, `LEN`, `MIN`/`MAX`) and
    **not** the `other` shape (`DATALENGTH`, no distinct), and `build_value_list_sql`
    builds a list for it. The same value under `dialect="sqlite"` keeps
    `declared_type == "TEXT"` and `category == "string"`.
10. All-`NULL` column → `declared_type == "unknown"`, `category == "string"`, `note` set.
11. Zero rows returned → every column resolves "unknown" without raising.
12. First value `NULL`, second non-`NULL` → the second decides the type.
13. Duplicate / empty / `":"`-suffixed names → rejection message naming aliasing.
14. The probe SQL passed to the backend contains `LIMIT 5` / `TOP 5` and the params dict is
    forwarded unchanged.

`tests/summarize/test_sql.py` — updated call sites plus:
15. `validate_where` against a `Subquery` ref builds its probe from the rendered subquery
    and returns the predicate AST.

`tests/summarize/test_render.py`
16. A `ColumnMeta` with `note` renders `(unknown, string — …)`; with `note == ""` the header
    is byte-identical to today.

`tests/summarize/test_tools.py`
17. **Unchanged.** The `core` call-site swap is behaviour-preserving; every existing
    `where`-path test must pass unedited.

## ACCEPTANCE

No user-visible change yet. All existing summarize tests pass (after the mechanical
`validate_where` updates); `sql.py` stays under 750 lines; all three MCP checks green.

## LLM PROMPT

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_3.md`.
>
> Implement step 3 only, test-first: create `src/mcp_tools_sql/summarize/source.py` with
> `validate_source` and `probe_columns`, add the `SourceRef` alias and the optional
> `ColumnMeta.note` field in `summarize/sql.py`, widen the `table_ref` hints, change
> `validate_where` to take the already-built `table_ref`, and render the inline note in
> `summarize/render.py`.
>
> The probe's Python-value → declared-type mapping takes the **dialect**: a `str` must type
> as `"nvarchar"` on `tsql`, never `"TEXT"`, or `categorize_type`'s LOB guard sweeps every
> string column into `other`. Test 9b is the regression guard for that.
>
> Write `tests/summarize/test_source.py` first. Update the ~12 `validate_where` call sites
> in `tests/summarize/test_sql.py` mechanically — do not change what they assert. Do not
> move any existing function between modules.
>
> `summarize/tools.py` gets **exactly one** edit in this step: `core` must build
> `table_ref` before calling `validate_where` and pass it in, because that is
> `validate_where`'s only production caller and the commit will not typecheck otherwise. Do
> not add `Source`, the `sql` parameter, or any notes plumbing to `tools.py` yet — those are
> steps 4 and 5.
>
> Use MCP tools for all file and check operations. When done, run
> `mcp__tools-py__run_pylint_check`, `mcp__tools-py__run_pytest_check`
> (`extra_args=["-n", "auto"]`), and `mcp__tools-py__run_mypy_check`, and fix everything
> they report. Do not start step 4.
