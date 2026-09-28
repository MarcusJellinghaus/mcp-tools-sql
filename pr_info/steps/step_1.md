# Step 1 — Rewrite `_DESCRIPTION` and the module docstring

Documentation only. No behaviour changes. Fixes the inverted cost advice that an
LLM caller reads to choose parameters.

## WHERE

- `src/mcp_tools_sql/summarize/tools.py` — `_DESCRIPTION` (module level, currently
  around line 76) and the module docstring line reading
  `per-column value lists (deep view only)` (around line 15).
- `tests/summarize/test_tools.py` — new test.

## WHAT

No signatures change. `_DESCRIPTION` stays a module-level `str` built from
concatenated literals.

The sentence to remove:

> The source is executed once per profiled column plus three times, so narrow
> with `columns=` on expensive queries.

Replacement content, stating four things:

1. At 15 or fewer profiled columns you **also** get per-column value lists, at
   one extra execution of the source per column — 3 queries become 3+N. So
   `columns=` trades breadth for depth; it does not reduce cost.
2. To reduce cost, filter with `where=`.
3. Or profile a subset with `sql=` carrying its own row limit.
4. Above 1,000,000 rows distinct counts and value lists are omitted.

Everything else in the current text is kept. The result may grow to roughly 1,400
characters (from ~1,050).

Suggested text (adjust wording freely; keep all four facts and every existing
sentence):

```python
_DESCRIPTION = (
    "Profile a table (schema+table) or an arbitrary read-only SELECT (sql) "
    "— supply one, not both. Per profiled column: row/null/distinct counts, "
    "category-appropriate statistics (min/max/mean/sum for numeric, date "
    "bounds for temporal, length stats for string, true/false counts for "
    "boolean, byte sizes for binary), and duplication-driven value lists "
    "(top values with frequencies when values repeat, a sample when every "
    "value is unique). Read-only. Narrow with columns= and filter with a "
    "read-only where predicate; the predicate must use :name placeholders "
    "for values, bound via params (never inline literals). With sql, the "
    "where predicate is applied OUTSIDE the query, so it can filter computed "
    "and aggregated columns. Returns a formatted text block; sources wider "
    "than 15 profiled columns render a compact one-line-per-column triage "
    "instead. At 15 or fewer profiled columns you also get per-column value "
    "lists, one extra execution of the source per column (3 queries become "
    "3+N), so columns= trades breadth for depth rather than reducing cost. "
    "To reduce cost, filter with where=, or profile a subset with sql= "
    "carrying its own row limit. Above 1,000,000 rows distinct counts and "
    "value lists are omitted. n sets the value-list length (default 20, "
    "clamped to 1..50)."
)
```

Module docstring: the pipeline line currently reads

> `-> per-column value lists (deep view only) -> render_summary`

Change the parenthetical to say the lists are fetched only in the deep view **and
only at or below the row gate**. Step 5 makes that true; wording it now keeps the
two documentation edits in one commit, and the docstring is not executable.

## HOW

`_DESCRIPTION` is already passed twice — to `build_tool_fn` and to
`mcp.add_tool(description=...)` — so no integration point changes. No imports
change.

## ALGORITHM

None.

## DATA

`_DESCRIPTION: str`.

## TDD

Write first, in `tests/summarize/test_tools.py` (import `_DESCRIPTION` from
`mcp_tools_sql.summarize.tools`):

```python
def test_description_advises_where_not_columns_for_cost() -> None:
    """The cost advice points at where=/sql=, and never at columns=."""
```

Assert: the removed sentence fragment `"so narrow with columns= on expensive"` is
absent; `"3+N"` (or however the per-column cost is phrased) is present;
`"where="` and `"sql="` appear in the cost guidance; `"1,000,000"` appears; and
`len(_DESCRIPTION) < 1_500`. Keep the assertions to the four facts — do not pin
the whole string, or every future wording tweak breaks the test.

## Commit

`docs(summarize): fix inverted columns= cost advice in the tool description`

## Checks

`run_format_code`, then `run_pylint_check`, `run_pytest_check` with
`extra_args: ["-n", "auto"]`, `run_mypy_check`.

## Prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_1.md`. Implement step 1
> only: rewrite `_DESCRIPTION` in `src/mcp_tools_sql/summarize/tools.py` so the
> cost advice points at `where=` and `sql=` instead of `columns=`, and correct the
> module docstring's value-list parenthetical. Write the test first. Change no
> behaviour. Run format, pylint, pytest (`-n auto`) and mypy, then make one
> commit.
