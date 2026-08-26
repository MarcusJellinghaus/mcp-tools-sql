# Step 4 — Refactor the table path onto `Source` (no behaviour change)

**Goal:** introduce the `Source` value object and make the whole pipeline source-agnostic,
while `summarize_columns` still accepts only `schema` + `table`. This is a pure refactor:
every existing test must pass **unchanged**, which is exactly what proves it.

**Depends on:** step 3. **Blocks:** step 5.

---

## WHERE

| File | Change |
|---|---|
| `src/mcp_tools_sql/summarize/source.py` | Gains `Source` and `build_table_source` |
| `src/mcp_tools_sql/summarize/render.py` | `empty_table_message` → `empty_source_message(label)`; `empty_filter_message(total_rows, label)` |
| `src/mcp_tools_sql/summarize/tools.py` | `_run` takes a `Source`; `core` builds one; notes footer plumbing |
| `tests/summarize/test_source.py` | `build_table_source` tests |
| `tests/summarize/test_render.py` | Message tests for both label states |

## WHAT

```python
# summarize/source.py
@dataclass(frozen=True)
class Source:
    ref: SourceRef                # exp.Table for a table, exp.Subquery for a query
    label: str | None             # "dbo.orders" / "orders" on SQLite; None for a query
    metas: list[ColumnMeta]
    notes: list[str]
    types_probed: bool

def build_table_source(
    backend: DatabaseBackend, schema: str, table: str, dialect: str
) -> Source | str: ...            # str == an error message to return to the caller
```

```python
# summarize/render.py
def empty_source_message(label: str | None) -> str: ...
def empty_filter_message(total_rows: int, label: str | None) -> str: ...
# table_not_found_message(schema, table) unchanged — no sql-path analogue
```

```python
# summarize/tools.py
def _run(                          # 10 params -> 8; schema/table/table_ref collapse into source
    backend: DatabaseBackend, rec: Any, source: Source,
    predicate: Any, params: dict[str, Any] | None,
    columns: list[str] | None, n: int, dialect: str,
) -> str: ...
```

## HOW

- `build_table_source` moves the metadata query and `ColumnMeta` assembly out of `_run`:
  it runs `metadata_sql(dialect)` with `{"schema": schema, "table": table}`, returns
  `table_not_found_message(schema, table)` when no rows come back, and otherwise builds a
  `Source` with `notes=[]` and `types_probed=False`.
- `label` is `f"{schema}.{table}"` on `tsql` and `table` on `sqlite` — matching what
  `build_table_ref` already does with the schema per decision 20. The messages prepend the
  word "Table".
- Message bodies branch on `label is None`; the table wording stays **byte-identical**:
  - `empty_source_message`: `Table dbo.orders is empty (0 rows). Use read_columns for its column definitions.` / `The source query returned 0 rows.`
  - `empty_filter_message`: `No rows match the where predicate (table has 50,000 rows).` / `… (source has 50,000 rows).`
- `core` calls `build_table_source` **before** `validate_where`, because `validate_where`
  now needs the ref (`source.ref`); the `str` return short-circuits.
- Notes footer plumbing: collect `source.notes` and the existing `clamp_note` into one list
  and join them into the trailing block. With a table source the list contains at most the
  clamp note, so the rendered output is unchanged today.

## ALGORITHM

```
core(...):
    built = build_table_source(backend, schema, table, dialect)
    if isinstance(built, str): return built
    predicate, err = validate_where(where, built.ref, params, dialect)
    if err: return err
    return _run(backend, rec, built, predicate, params, columns, n, dialect)

_run(...):
    narrowed = _narrow_columns(source.metas, columns)         # unchanged
    rows = count(...);  if rows == 0:
        return empty_filter_message(total, source.label) if predicate else empty_source_message(source.label)
    ... scalar pass, value lists, render_summary ...          # unchanged
    footer = [*source.notes, clamp_note if clamp_note else ...]
    return summary if not footer else summary + "\n\n" + "\n".join(footer)
```

## DATA

`Source` as above; `build_table_source` returns `Source | str` following the existing
`_narrow_columns` idiom (`str` means "return this text to the caller").

## TESTS (write first)

`tests/summarize/test_source.py`
1. `build_table_source` on a MagicMock backend returns a `Source` whose `metas` match the
   metadata rows, `label` is `dbo.orders` on tsql and `orders` on sqlite, `notes == []`,
   `types_probed is False`.
2. Empty metadata rows → the exact `table_not_found_message` text.

`tests/summarize/test_render.py`
3. `empty_source_message(None)` → `The source query returned 0 rows.`
4. `empty_source_message("dbo.orders")` → byte-identical to today's `empty_table_message`
   output (keep the existing exact-wording assertion, retargeted).
5. `empty_filter_message(50_000, None)` says "source has"; with a label, "table has" —
   again byte-identical to today.

`tests/summarize/test_tools.py`
6. **Unchanged.** Every existing test passing untouched is the acceptance criterion for
   this step. Do not edit them beyond what a renamed import forces.

## ACCEPTANCE

Zero user-visible change. `tests/summarize/test_tools.py` passes without edits to
assertions; `_run`'s parameter count drops (drop the `# noqa: PLR0913` if pylint no longer
needs it); all three MCP checks green.

## LLM PROMPT

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_4.md`.
>
> Implement step 4 only, test-first: add the `Source` dataclass and `build_table_source` to
> `src/mcp_tools_sql/summarize/source.py`, retarget the two status messages in
> `summarize/render.py` to take a source label, and refactor `summarize/tools.py` so `core`
> builds a `Source` and `_run` consumes it.
>
> This is a **pure refactor**: `summarize_columns` still takes only `schema` and `table`,
> and every assertion in `tests/summarize/test_tools.py` must pass unedited. Keep the table
> path's message wording byte-identical. Do not add the `sql` parameter yet.
>
> Use MCP tools for all file and check operations. When done, run
> `mcp__tools-py__run_pylint_check`, `mcp__tools-py__run_pytest_check`
> (`extra_args=["-n", "auto"]`), and `mcp__tools-py__run_mypy_check`, and fix everything
> they report. Do not start step 5.
