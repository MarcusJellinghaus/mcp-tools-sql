# Step 5 — Apply the gate uniformly to distinct counts and value lists

One threshold, one rule, independent of column count. This is the behavioural
core of the issue.

## WHERE

- `src/mcp_tools_sql/summarize/tools.py` — `_run`, the two lines at 418-419 and
  the value-list guard at ~431.
- `src/mcp_tools_sql/summarize/render.py` — three stale comments / docstrings that
  describe the gate as triage-only.
- `tests/summarize/test_tools.py` — `_fake_scalar_row` / `_gate_backend` stop
  emitting a `__distinct` alias the SQL never asked for;
  `test_distinct_gate_deep_never_gated` inverts; new value-list-skip coverage.

## WHAT

**The rule.** Drop the `view == "deep" or` override:

```python
view = "triage" if len(profiled) > TRIAGE_THRESHOLD else "deep"
# One row-count gate, independent of the view: above it the source gets the
# count and scalar queries only -- no COUNT(DISTINCT), no per-column value
# lists. Narrowing with columns= cannot switch it back on.
include_distinct = rows <= DISTINCT_GATE_ROWS
```

**The value-list skip.** One extra term on the existing guard:

```python
if include_distinct and view == "deep" and meta.category != "other" and non_null > 0:
```

Nothing else in the loop needs restructuring: `value_kind` is already initialised
to `"none"` and `values` to `None` immediately above the guard, so a gated column
gets `value_kind="none"` **explicitly** rather than falling through to the
`"sample"` that the `distinct is None` / `values is None` combination would
otherwise compute.

**Do not rename `include_distinct`.** The issue leaves it to the implementer; the
name still describes the keyword argument it feeds to `build_scalar_sql`, and the
comment above it states that it governs value lists too. Renaming buys nothing and
touches three more places.

**Stale comments and docstrings in `render.py`** — all three describe the gate as a
triage-only affair:

- the `_BLANK` comment (line 41): "gated out of triage" → gated out by the row
  gate, in either view.
- the `DISTINCT_GATE_ROWS` comment (lines 53-54): "above which triage omits
  `COUNT(DISTINCT)`" → above which **both views** omit `COUNT(DISTINCT)` **and**
  the per-column value lists; the footer states the reason.
- `ColumnProfile.distinct`'s docstring (lines 78-81): "gated out (triage over a
  large table)" → gated out by the row gate, in either view.

## HOW

No signature changes and no new imports — `DISTINCT_GATE_ROWS` and
`TRIAGE_THRESHOLD` are already imported in `tools.py`. `build_scalar_sql`'s
`include_distinct=` keyword keeps its current meaning.

## ALGORITHM

```
rows = count query
include_distinct = rows <= DISTINCT_GATE_ROWS
scalar_row = scalar query (include_distinct=include_distinct)
for each profiled column:
    value_kind, values = "none", None
    if include_distinct and deep and category != "other" and non_null > 0:
        fetch the top/sample list          # skipped entirely above the gate
```

Query count above the gate: 2 (count + scalar), down from N+2. Below the gate:
unchanged.

## DATA

Above the gate every `ColumnProfile` carries `distinct=None`, `values=None`,
`value_kind="none"`. Visible result — the deep view's distinct cell is blank on
every block:

```
Status  (varchar, string)
  rows 2,000,000 | nulls 0 (0.0%) | empty 0 (0.0%) | distinct —
  length  min 3 | max 9 | avg 5.1
```

…with `distinct_gate_note()` in the footer (wired in step 4) naming the recovery:
`where=` to get under a million, or `sql=` with a row limit.

## TDD

**Fix the fake first.** `_fake_scalar_row` (test_tools.py:325-337) emits
`c{i}__distinct = 10` unconditionally, and `_split_stats` pops whatever alias is
present regardless of `include_distinct` — so a gated call currently yields
`distinct=10` and renders `distinct 10`. The fake must model the real scalar
pass: the `__distinct` alias exists only when the SQL asked for it. Give
`_fake_scalar_row` an `include_distinct: bool = True` parameter that omits the
`c{i}__distinct` keys when `False`, and have `_gate_backend`'s `fake` decide per
call from the SQL it was handed:

```python
if "c0__nonnull" in sql:
    captured["scalar_sql"] = sql
    return [_fake_scalar_row(n_cols, include_distinct="COUNT(DISTINCT" in sql)]
```

(build the row inside `fake` instead of once up front, since it now depends on
the emitted SQL). Every existing `_gate_backend` caller is unaffected: below the
gate the SQL still carries `COUNT(DISTINCT`, so the alias is still present.

**Invert** `test_distinct_gate_deep_never_gated` (test_tools.py:372). It currently
pins the bug. Same `_gate_backend(n_cols=3, row_count=2_000_000)` fixture, new
subject:

```python
async def test_distinct_gate_applies_to_deep_view() -> None:
    """A deep call above the row gate omits distinct, like triage does."""
    backend, captured = _gate_backend(n_cols=3, row_count=2_000_000)
    ...
    assert "(INTEGER, numeric)" in out          # still the deep view
    assert "COUNT(DISTINCT" not in captured["scalar_sql"]
    assert "distinct —" in out                  # needs the fake fix above
    assert "distinct counts and value lists omitted" in out
```

**New**, same file — the value-list skip is the cost win and needs its own proof.
`_gate_backend`'s fake returns `[{"value": 1, "freq": 5}]` for anything it does not
recognise, so count the calls instead: capture every SQL string passed to
`backend.execute_readonly_query` (the MagicMock records them in `call_args_list`)
and assert that above the gate exactly two queries follow the metadata lookup, and
that no `GROUP BY` / `LIMIT` value-list query was issued.

```python
async def test_value_lists_skipped_above_the_gate() -> None:
    """Above the gate no per-column value list is fetched, in either view."""
```

Assert both: `"top values:"` and `"sample values"` are absent from the output.

**New**, same file — the counterpart below the gate, so the skip cannot silently
become unconditional:

```python
async def test_value_lists_still_fetched_below_the_gate() -> None:
    """A deep call at or below the gate keeps its per-column value lists."""
```
`_gate_backend(n_cols=3, row_count=1_000_000)` — exactly at the threshold, which
`<=` includes. Assert a value list renders and `"COUNT(DISTINCT"` is in the scalar
SQL.

## Commit

`fix(summarize): apply the row-count gate uniformly to distinct and value lists`

## Checks

`run_format_code`, `run_pylint_check`, `run_pytest_check` with
`extra_args: ["-n", "auto"]`, `run_mypy_check`.

## Prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_5.md`. Implement step 5
> only: in `src/mcp_tools_sql/summarize/tools.py` make `include_distinct` read
> `rows <= DISTINCT_GATE_ROWS` alone and add it as a term to the value-list guard,
> then correct the three stale gate comments/docstrings in `render.py`. First fix
> `_fake_scalar_row` / `_gate_backend` so the `__distinct` alias is absent when the
> scalar SQL carries no `COUNT(DISTINCT)`, then invert
> `test_distinct_gate_deep_never_gated` and add the two value-list tests. Do
> not rename `include_distinct`, do not add a second threshold, and do not touch
> the triage `columns=` hint. Run format, pylint, pytest (`-n auto`) and mypy, then
> make one commit.
