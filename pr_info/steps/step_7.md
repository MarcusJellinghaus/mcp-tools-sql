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
_DESCRIPTION: str   # module-level constant, see below

def _base_summarize_params() -> list[inspect.Parameter]:
    # schema, table, columns, where, params, n  (POSITIONAL_OR_KEYWORD)

class SummarizeTools:
    def __init__(self, registry: BackendRegistry, targets: ResolvedTargets) -> None: ...
    def register(self, mcp: FastMCP) -> None: ...   # builds core + build_tool_fn
```

`async def core(schema, table, columns=None, where=None, params=None, n=20, *,
connection=None, database=None) -> str` — **`async`**, exactly as
`count_tools.py:135`: `build_tool_fn` awaits `body(**kwargs)`, so a plain
`def core` would break at call time.

### Tool description (required by `build_tool_fn` **and** `mcp.add_tool`)

Both `build_tool_fn(name, sig_params, body, doc)` and
`mcp.add_tool(fn, name=..., description=...)` take the description, so a
module-level `_DESCRIPTION` constant is mandatory (mirroring
`count_tools._DESCRIPTION`). It must advertise the `:name`-placeholder contract
the issue requires:

```python
_DESCRIPTION = (
    "Profile the data in a table's columns: row/null/distinct counts, "
    "category-appropriate statistics (min/max/mean/sum for numeric, date "
    "bounds for temporal, length stats for string, true/false counts for "
    "boolean, byte sizes for binary), and duplication-driven value lists "
    "(top values with frequencies when values repeat, a sample when every "
    "value is unique). Read-only. Narrow with columns= and filter with a "
    "read-only where predicate; the predicate must use :name placeholders "
    "for values, bound via params (never inline literals). Returns a "
    "formatted text block; tables wider than 15 profiled columns render a "
    "compact one-line-per-column triage instead. n sets the value-list "
    "length (default 20, clamped to 1..50)."
)
```

## HOW — `core` pipeline (mirrors `count_tools.CountTools.register`)

1. `target = targets.resolve_pinned(connection, database)` (catch `ValueError`
   → return `str(exc)`); `backend = registry.backend_for(target)`;
   `dialect = to_dialect(target.backend_name)`; open `log_tool_call`.

   **Logging contract.** Open
   `async with log_tool_call("summarize_columns", params or {}, sql=where or "")
   as rec:` — the logged `sql=` is the **user's raw `where` text** (empty string
   when no predicate), not any generated query: the generated SQL is derived,
   multi-query (metadata + count + scalar + one per value list) and would flood
   the log line, whereas `where` is the only SQL the caller wrote. Call
   `rec.record(rows=len(profiled), cols=1)` once the profiled column set is
   known (step 5 below) — one rendered block/line per profiled column, one text
   result — **explicitly**, because omitting the call leaves the success log
   line reporting `rows=0 cols=0`. Early-return paths that fire *before*
   narrowing (target/where validation error, table-not-found) keep the default
   `0/0`, which is accurate there.
2. `validate_where(...)` → predicate or error string (return on error).

   **Param threading:** the re-rendered predicate carries the user's `:name`
   placeholders, so the user `params` dict must be passed as the second argument
   to `backend.execute_readonly_query` for **every** data query that embeds the
   predicate — the filtered `build_count_sql`, `build_scalar_sql`, and each
   `build_value_list_sql` — not only the metadata query. Otherwise a `where`
   using placeholders parses and validates but fails at execution with an
   unbound-parameter error. Two queries carry **no** predicate and therefore no
   placeholders: the metadata query (takes its own `{schema, table}` dict), and
   the empty-filter *unfiltered* count issued in step 6's zero-match branch
   (built with `predicate=None`, so it embeds nothing to bind — passing `params`
   there is harmless but unnecessary).
3. Run `metadata_sql(dialect)` with `{schema, table}` via
   `backend.execute_readonly_query`. No rows means the table does **not exist**
   (`INFORMATION_SCHEMA.COLUMNS` / `pragma_table_info` return zero rows only for
   an unknown table — an existing table always has columns), so return
   `table_not_found_message`, **not** `empty_table_message` (which asserts the
   table exists but holds 0 rows).
4. Build `ColumnMeta` list (`categorize_type` per row, keep ordinal).
5. **Narrow** by `columns` (case-insensitive match; unknown →
   `unknown_columns_message`; **explicitly empty list** →
   `empty_columns_message`; **de-duplicate** case-insensitively, preserving
   first-seen order; echo declared casing). **Cap** to first 50 by ordinal
   (`total_columns` retained for the footer). See the narrowing ALGORITHM below
   for both guards — each returns **before** any data query is issued.
6. `build_count_sql` → `rows` (the **filtered** count). `rows == 0` →
   - predicate supplied → issue an **unfiltered** `build_count_sql(table_ref,
     predicate=None, dialect)` to get the true table total, then
     `empty_filter_message(total_rows)` — so the message reads
     `No rows match the where predicate (table has N rows)` with the real
     total, never the filtered `0`. (This extra count runs **only** in this
     zero-match-with-predicate branch, so the normal path keeps its query
     budget.)
   - no predicate → `empty_table_message` (the filtered count *is* the total).
7. `view = "triage" if len(profiled) > TRIAGE_THRESHOLD else "deep"`;
   `include_distinct = view == "deep" or rows <= DISTINCT_GATE_ROWS`
   (`DISTINCT_GATE_ROWS = 1_000_000`, imported from `summarize.render` beside
   `TRIAGE_THRESHOLD`/`COLUMN_CAP` — **no inline literal**, matching the
   `VALUE_LIST_HARD_CAP` convention). The deep view is never gated by design.
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
   `clamp_note` still reports the clamp.) Every column that does **not** get a
   value list — the whole triage view, and every `other`-category column in the
   deep view — takes `kind = "none"`, `values = None`.
10. Build `ColumnProfile`s; `return render_summary(profiles, total_columns,
    distinct_gated=not include_distinct) + clamp_note`. `render_summary` takes
    **no `n`** (step 5/6): `clamped_n` is consumed by the value-list SQL only,
    and the renderer derives every printed count from the profile
    (`len(values)`, `p.distinct`), so a header can never claim more values than
    were actually returned.

    **`ColumnProfile` construction (all seven fields, always explicit).** The
    dataclass is frozen and declares **no defaults**, so every field is passed
    at every construction site:

    - `meta` / `rows` — the `ColumnMeta` and the filtered `COUNT(*)` from
      step 6 (the same `rows` for every column).
    - `non_null` / `distinct` / `stats` — read out of the single scalar row by
      the `c{idx}__{stat}` aliases; `distinct` is `None` whenever the alias was
      not emitted (gated out, or an `other`/binary column).
    - `values` — **dict rows must be mapped to tuples.**
      `backend.execute_readonly_query` returns `list[dict[str, Any]]`
      (`backends/base.py:35-37`) while `ColumnProfile.values` is
      `list[tuple[Any, ...]] | None`, so convert by the aliases
      `build_value_list_sql` emits:
      - `kind == "top"` → `[(r["value"], r["freq"]) for r in rows]`
      - `kind == "sample"` → `[(r["value"],) for r in rows]`

      This is what makes `for value, freq in values` in `_render_values`
      (step 5) type-check and unpack.
    - `value_kind` — `"top"` / `"sample"` / `"none"` as chosen in step 9.

    **Triage and other/binary columns carry no value list.** Value lists are
    built in the deep branch only, and never for `other`-category columns, so
    every profile outside that branch is constructed with the explicit pair
    `value_kind="none", values=None` — not omitted (there are no defaults to
    fall back on). `render_summary`'s triage path ignores both, and
    `_render_values` short-circuits on `value_kind == "none"`.

Wrap the DB calls in the same exception-mapping tail as `count_tools`
(`_INVALID_SQL_EXC`, `KeyError/TypeError/ValueError`, `RuntimeError`, `Exception`).
Signature: `_base_summarize_params() + build_target_params(targets, star=False)`.

## ALGORITHM (column narrowing)

```
by_lower = {m.name.lower(): m for m in metas}
available = [m.name for m in metas]
if columns is None: chosen = metas
else:
    if not columns:                          # explicitly empty list
        return empty_columns_message(available)
    bad = [c for c in columns if c.lower() not in by_lower]
    if bad: return unknown_columns_message(bad, available)
    seen: set[str] = set()                   # de-duplicate, first-seen order
    chosen = []
    for c in columns:
        key = c.lower()
        if key in seen: continue
        seen.add(key)
        chosen.append(by_lower[key])
total_columns = len(chosen); profiled = sorted(chosen, key=ordinal)[:COLUMN_CAP]
```

Both guards run **before** any data query.

- **Empty list.** `columns=[]` is *not* the same as `columns=None` (all
  columns): `bad` would be empty so no error fires, `chosen`/`profiled` would be
  empty, and `build_scalar_sql([])` renders `SELECT FROM "t"` — which the
  backend rejects with the opaque `Invalid SQL. OperationalError: near "FROM"`.
  Fail the call with `empty_columns_message` (same error class as the
  unknown-column error) instead.
- **Duplicates.** `columns=["a", "A", "a"]` must profile `a` once. Without the
  de-duplication the same column renders as three blocks, `total_columns` is
  inflated (wrong cap footer), and a 15-name call with repeats can flip past
  `TRIAGE_THRESHOLD` into triage. Keys are lower-cased (the same
  case-insensitive matching used for lookup), and first-seen order is preserved
  so the ordinal sort below is deterministic either way.

## DATA

`core` returns a single `str` (block/triage/message). One tool registered as
`summarize_columns`.

## WIRING

- `tach.toml`: add `[[modules]] path = "mcp_tools_sql.summarize"` (layer
  `tool_implementation`, `depends_on` = backends, formatting, tool_logging,
  query_helpers, tool_builder, utils). **No `config`** — matching
  `summary.md` § 1 and the `count_tools` precedent (`tach.toml:88-96` lists no
  `config`; its `ResolvedTargets` import is `TYPE_CHECKING`-only, which tach
  does not count as a dependency). Add `summarize` beside `count_tools` in
  `server`'s `depends_on`.
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
- **Param threading end-to-end**: a `where` using a `:name` placeholder *with*
  a matching `params` dict (e.g. `where="category = :cat"`,
  `params={"cat": "x"}`) that **matches rows** → a normal deep block whose
  counts reflect only the filtered subset. This is the only test that binds
  params through the whole pipeline (count + scalar + value-list queries); the
  `validate_where` unit tests (`step_2.md`) exercise validation in isolation and
  the nothing-matching `where` test above never reaches the scalar/value-list
  queries, so neither would catch a dropped `params` argument. Assert the result
  is **not** an `Invalid parameters.`/unbound-parameter error string.
- Non-existent table (`table="no_such_table"`) → table-not-found message
  (distinct from the empty-table wording).
- Unknown `columns=["Nope"]` → unknown-column message (declared casing echoed).
- **Empty `columns=[]`** → empty-columns message; assert it is **not** an
  `Invalid SQL.` string (proves the guard fires before any data query).
- **Duplicate `columns=["a", "A", "a"]`** → the column's block appears exactly
  once, and no cap footer / triage switch is triggered by the repeats.
- Wide table (> 15 cols) → triage; narrowed `columns=[…]` (≤ 15) → deep.
- **Distinct-gate decision** (invariant, `summary.md` § invariants): a triage
  call with `rows > DISTINCT_GATE_ROWS` builds the scalar SQL with
  `include_distinct=False` and renders the gate footer, while `rows <=
  DISTINCT_GATE_ROWS` keeps distinct; a **deep** call is never gated regardless
  of `rows`. Drive it with a `MagicMock`/`RecordingRegistry` backend returning a
  synthetic `row_count` above the threshold (no million-row fixture) and assert
  on the issued SQL (`COUNT(DISTINCT` present/absent).
- `n` clamp note appears for `n=999`; `n=0` clamps to 1 (note present, no empty
  `top values:` block).
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
> `pr_info/steps/summary.md`). Create `summarize/tools.py` with `_DESCRIPTION`
> (advertising the `:name`-placeholder/`params` contract),
> `_base_summarize_params` and `SummarizeTools` (mirroring
> `count_tools.CountTools`): resolve the pinned target per call, then an
> **`async def core`** running the metadata → narrow/cap → `COUNT(*)`
> short-circuit → scalar pass → value-lists → `render_summary` pipeline, with
> the `count_tools` exception tail. Reject an empty `columns=[]` and de-duplicate
> repeated names before any data query; thread `params` into every
> predicate-bearing query; log via `log_tool_call(..., sql=where or "")` with an
> explicit `rec.record`. Export it
> from the package `__init__`, add `"summarize_columns"` to
> `PROGRAMMATIC_BUILTIN_TOOLS`, register it in `server.py`, add the
> `mcp_tools_sql.summarize` module to `tach.toml` and `.importlinter`, and
> update the roadmap in `mcp-tools-sql.md`. Add the `profiling_db` fixture and
> end-to-end SQLite tests plus a `MagicMock` T-SQL dialect check. Run pylint,
> pytest (`-n auto`), mypy, `run_tach_check`, and `run_lint_imports_check`; fix
> everything; one commit.
