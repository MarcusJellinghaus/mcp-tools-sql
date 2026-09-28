# Step 3 — Reword the `distinct is None` sample header

A one-string change. `_render_values`' fallback header claims a distinct count
nobody measured.

## WHERE

- `src/mcp_tools_sql/summarize/render.py` — `_render_values`, the `else` branch of
  `if p.distinct is not None` in the sample section.
- `tests/summarize/test_render.py` — `test_sample_distinct_none_omits_of_clause`
  (currently line 339).

## WHAT

Current:

```python
header = f"  sample values ({_fmt_int(len(values))} distinct values):"
```

renders `sample values (3 distinct values):` — asserting that the 3 shown values
are the only 3 distinct ones, which was never counted. New:

```python
header = f"  sample values ({_fmt_int(len(values))} shown):"
```

**Keep the branch.** `if p.distinct is not None` needs an else, and the renderers
are unit-tested directly even where the pipeline cannot reach a state. Once
step 5 lands, the pipeline cannot produce a sample list with `distinct is None`
at all — the branch is reachable only from tests, and that is fine.

The disclosed variant — `sample values (20 of 500,000 distinct — every value
unique):` — is **unchanged**. It already gives the count.

## HOW

No signature, import or docstring changes. Mention in `_render_values`' docstring
that the fallback header names only the shown count, since it has no distinct
total to name.

## ALGORITHM

None.

## DATA

The rendered header line.

## TDD

Update the existing test rather than adding one — it keeps its subject:

```python
def test_sample_distinct_none_omits_of_clause() -> None:
    """A sample list with distinct=None names only the shown count."""
    ...
    assert "  sample values (2 shown):" in out
    assert " of " not in out
    assert "distinct values" not in out   # no unmeasured count is asserted
```

Run it and watch it fail on the old string before changing `render.py`.

## Commit

`fix(summarize): sample header names the shown count, not an unmeasured distinct`

## Checks

`run_format_code`, `run_pylint_check`, `run_pytest_check` with
`extra_args: ["-n", "auto"]`, `run_mypy_check`.

## Prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_3.md`. Implement step 3
> only: change the `distinct is None` sample header in `_render_values`
> (`src/mcp_tools_sql/summarize/render.py`) to `sample values (N shown):`, keeping
> the branch. Update `test_sample_distinct_none_omits_of_clause` first and see it
> fail. Leave the disclosed `N of D distinct` header alone. Run format, pylint,
> pytest (`-n auto`) and mypy, then make one commit.
