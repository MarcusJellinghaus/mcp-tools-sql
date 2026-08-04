# Step 7 — `SummarizeTools` orchestration + registration + wiring

Assemble the pipeline into the tool, register it, wire the architecture
boundaries, and prove it end-to-end on SQLite. See `pr_info/steps/summary.md`
(§ Tool contract, § Execution pipeline, § Files created/modified).

## WHERE

- Create `src/mcp_tools_sql/summarize/tools.py`.
- Edit `src/mcp_tools_sql/summarize/__init__.py` — `from .tools import SummarizeTools`.
- Edit `src/mcp_tools_sql/schema_tools.py` — add `"summarize_columns"` to
  `PROGRAMMATIC_BUILTIN_TOOLS`.
- Edit `src/mcp_tools_sql/server.py` — `SummarizeTools(self._registry,
  self._targets).register(self._mcp)` in `_register_builtin_tools`.
- Edit `tach.toml` and `.importlinter` — add `mcp_tools_sql.summarize`.
- Edit `mcp-tools-sql.md` — roadmap `read_table_profile` → `summarize_columns`.
- Create `tests/summarize/conftest.py`, `tests/summarize/test_tools.py`.

## WHAT

```python
def _base_summarize_params() -> list[inspect.Parameter]:
    # schema, table, columns, where, params, n  (POSITIONAL_OR_KEYWORD)

class SummarizeTools:
    def __init__(self, registry: BackendRegistry, targets: ResolvedTargets) -> None: ...
    def register(self, mcp: FastMCP) -> None: ...   # builds core + build_tool_fn
```

`core(schema, table, columns=None, where=None, params=None, n=20, *,
connection=None, database=None) -> str`.

## HOW — `core` pipeline (mirrors `count_tools.CountTools.register`)

1. `target = targets.resolve_pinned(connection, database)` (catch `ValueError`
   → return `str(exc)`); `backend = registry.backend_for(target)`;
   `dialect = to_dialect(target.backend_name)`; open `log_tool_call`.
2. `validate_where(...)` → predicate or error string (return on error).
3. Run `metadata_sql(dialect)` with `{schema, table}` via
   `backend.execute_readonly_query`. No rows means the table does **not exist**
   (`INFORMATION_SCHEMA.COLUMNS` / `pragma_table_info` return zero rows only for
   an unknown table — an existing table always has columns), so return
   `table_not_found_message`, **not** `empty_table_message` (which asserts the
   table exists but holds 0 rows).
4. Build `ColumnMeta` list (`categorize_type` per row, keep ordinal).
5. **Narrow** by `columns` (case-insensitive match; unknown →
   `unknown_columns_message`; echo declared casing). **Cap** to first 50 by
   ordinal (`total_columns` retained for the footer).
6. `build_count_sql` → `rows`. `rows == 0` → `empty_filter_message` when a
   predicate was supplied, else `empty_table_message`.
7. `view = "triage" if len(profiled) > TRIAGE_THRESHOLD else "deep"`;
   `include_distinct = view == "deep" or rows <= 1_000_000`.
8. `build_scalar_sql(..., include_distinct=...)` → one row; assemble stats per
   column from the `c{idx}__{stat}` aliases.
9. `clamped_n, clamp_note = clamp_n(n)` **before** the view dispatch, so
   `clamp_note` is always bound regardless of view. If deep: for each
   non-`other` column pick `kind`:
   - `non_null == 0` (all-NULL / empty column) → `kind = "none"` (no value
     list). Skip the value-list query — a lone `NULL` sample row renders the
     nonsensical `sample values (1 of 0 distinct — every value unique)`, and an
     empty column carries no values to sample.
   - else `distinct < non_null → top`; `distinct == non_null → sample`.

   Run `build_value_list_sql(..., clamped_n, ...)` for the `top`/`sample`
   columns. (Triage has no value lists, so `clamped_n` is unused there, but
   `clamp_note` still reports the clamp.)
10. Build `ColumnProfile`s; `return render_summary(profiles, total_columns,
    clamped_n, distinct_gated=not include_distinct) + clamp_note`. Pass
    **`clamped_n`**, not the raw `n`, so the sample-values header count never
    exceeds the 50-value cap. The renderer derives the *shown* count from
    `len(values)` (not from any `n`), so the header stays correct even when
    fewer than `clamped_n` distinct values exist.

Wrap the DB calls in the same exception-mapping tail as `count_tools`
(`_INVALID_SQL_EXC`, `KeyError/TypeError/ValueError`, `RuntimeError`, `Exception`).
Signature: `_base_summarize_params() + build_target_params(targets, star=False)`.

## ALGORITHM (column narrowing)

```
by_lower = {m.name.lower(): m for m in metas}
if columns is None: chosen = metas
else:
    bad = [c for c in columns if c.lower() not in by_lower]
    if bad: return unknown_columns_message(bad, [m.name for m in metas])
    chosen = [by_lower[c.lower()] for c in columns]
total_columns = len(chosen); profiled = sorted(chosen, key=ordinal)[:50]
```

## DATA

`core` returns a single `str` (block/triage/message). One tool registered as
`summarize_columns`.

## WIRING

- `tach.toml`: add `[[modules]] path = "mcp_tools_sql.summarize"` (layer
  `tool_implementation`, `depends_on` = backends, config, formatting,
  tool_logging, query_helpers, tool_builder, utils). Add `summarize` beside
  `count_tools` in `server`'s `depends_on`.
- `.importlinter`: add `mcp_tools_sql.summarize` to the tool layer line
  (sibling of `count_tools`).
- Run `mcp__mcp-tools-py__run_tach_check` and `run_lint_imports_check` — both
  must pass.

## TESTS

`tests/summarize/conftest.py` — a `profiling_db` SQLite fixture with a table
carrying: an integer column (with a zero and a negative), a text column with
duplicates + a NULL + a whitespace value, a unique-key text column, a date
column, a boolean column (mixed true/false + a NULL), and an all-NULL column
(to exercise the `non_null == 0` → `value_kind == "none"` path).

`tests/summarize/test_tools.py`:

- End-to-end deep view for a duplicated column → asserts nulls/empty/distinct
  line + `top values` + remainder.
- Unique-key column → `sample values (… every value unique)`; assert the header
  count equals the number of values shown, and that `n=999` (clamped to 50)
  never yields a header claiming `999`.
- Numeric column → min/max/mean/zero/negative counts correct.
- Date (temporal) column → deep block renders `min`/`max` bounds and distinct.
- Boolean column → deep block renders the `true/false/null` counts and `true %`
  (the boolean distinct-stat shape).
- All-NULL column → nulls line `100%`, **no** value-list section (verifies the
  `value_kind == "none"` short-circuit; no `sample values (1 of 0 …)`).
- Zero-row table → empty-table message; `where` matching nothing → empty-filter
  message.
- Non-existent table (`table="no_such_table"`) → table-not-found message
  (distinct from the empty-table wording).
- Unknown `columns=["Nope"]` → unknown-column message (declared casing echoed).
- Wide table (> 15 cols) → triage; narrowed `columns=[…]` (≤ 15) → deep.
- `n` clamp note appears for `n=999`.
- Registration: `SummarizeTools(*single_target(backend)).register(mcp)` then
  `list_tools()` exposes `summarize_columns`; multi-target install surfaces
  `connection`/`database` props but **not** `"*"`.
- One MSSQL `MagicMock` test asserting the metadata/scalar SQL is issued under
  the `tsql` dialect (rendered-SQL parity, no live server).

Use `create_connected_server_and_client_session` and the `single_target` /
`RecordingRegistry` helpers from `tests/target_helpers.py`.

## COMMIT

`feat(summarize): register summarize_columns tool and wire boundaries`

## PROMPT

> Implement Step 7 from `pr_info/steps/step_7.md` (context in
> `pr_info/steps/summary.md`). Create `summarize/tools.py` with
> `_base_summarize_params` and `SummarizeTools` (mirroring
> `count_tools.CountTools`): resolve the pinned target per call, run the
> metadata → narrow/cap → `COUNT(*)` short-circuit → scalar pass → value-lists
> → `render_summary` pipeline, with the `count_tools` exception tail. Export it
> from the package `__init__`, add `"summarize_columns"` to
> `PROGRAMMATIC_BUILTIN_TOOLS`, register it in `server.py`, add the
> `mcp_tools_sql.summarize` module to `tach.toml` and `.importlinter`, and
> update the roadmap in `mcp-tools-sql.md`. Add the `profiling_db` fixture and
> end-to-end SQLite tests plus a `MagicMock` T-SQL dialect check. Run pylint,
> pytest (`-n auto`, fast markers), mypy, `run_tach_check`, and
> `run_lint_imports_check`; fix everything; one commit.
