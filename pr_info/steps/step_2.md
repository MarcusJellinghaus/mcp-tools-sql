# Step 2 — `_clamp0`, applied at the three cross-query subtraction sites

The pipeline runs N+2 queries with no snapshot and the renderer subtracts across
them, so a concurrent write can make a printed count negative. Floor all three
subtractions at zero through one helper.

## WHERE

`src/mcp_tools_sql/summarize/render.py` only:

- new `_clamp0`, beside `_fmt_int` / `_fmt_pct` in the helper block.
- `_render_block` — `nulls = p.rows - p.non_null`.
- `render_triage` — the same expression inside the per-profile loop.
- `_render_values` — `rem_rows = rows - shown_rows`, and the `_fmt_pct` that
  reads it.

Tests: a **new** module `tests/summarize/test_render_clamp.py` — not
`test_render.py`. That file is already 719 lines against the 750-line limit CI
enforces (`mcp-coder check file-size`, `.github/workflows/ci.yml:74`; the
allowlist exempts only `mcp-tools-sql.md`), and the three tests below are roughly
50 lines, so adding them there breaks this step's own commit. Step 4's later
deletion of `test_triage_gated_blanks_distinct_and_notes_reason` is ~10 lines and
does not recover it. The new module has a coherent subject of its own — the
cross-query count arithmetic — and step 6 has no reason to touch it.

## WHAT

```python
def _clamp0(n: int) -> int:
    """Floor a count at zero.

    The profiling pipeline runs its count, scalar and value-list queries
    separately with no snapshot, so a concurrent write between them can make a
    difference of two counts negative (``rows`` from one query, ``non_null`` or
    a frequency sum from another). Printing ``nulls -3`` would be worse than
    printing ``0``; ``tools.py`` detects the same skew and appends a footer note
    saying the counts disagreed.

    Returns:
        ``n``, or ``0`` when ``n`` is negative.
    """
    return max(0, n)
```

Call sites become `nulls = _clamp0(p.rows - p.non_null)` (twice) and
`rem_rows = _clamp0(rows - shown_rows)`.

## HOW

Module-private, no imports, no signature changes. `_fmt_pct(rem_rows, rows)`
needs no edit — it reads the already-clamped local, so the percentage clamps with
it.

## ALGORITHM

Keep the helper a one-liner. Do **not** inline `max(0, …)` at the three sites:
the named helper is where the reason for the clamp is documented, and the issue
requires one helper used by all three.

Note what is deliberately **not** clamped: `zero` / `neg` / `empty` / `true` /
`false` come from the scalar query but are percentaged against `rows` from the
count query, so the same skew can push those percentages above 100%. They print
uncapped — consistent with printing a clamped remainder line rather than hiding
it. Step 6 detects them.

## DATA

`_clamp0(n: int) -> int`. Rendered output is unchanged for every consistent
profile.

## TDD

Write first, in the new `tests/summarize/test_render_clamp.py`. It needs its own
imports (`ColumnProfile`, `render_deep`, `render_triage` from
`mcp_tools_sql.summarize.render`) and its own local `_meta` helper — copy the
small builder `test_render.py` uses rather than importing across test modules.

```python
def test_deep_block_clamps_negative_nulls() -> None:
    """non_null > rows cannot print a negative null count."""
```
Build a `ColumnProfile` with `rows=100, non_null=120`, `value_kind="none"`.
Assert `"nulls 0 (0.0%)"` is in the output and `"-20"` is not.

```python
def test_triage_clamps_negative_nulls() -> None:
```
Same profile through `render_triage([p], total_columns=1, distinct_gated=False)`
— `distinct_gated` is still a parameter at this step. Assert `"0.0%"` present,
no `"-"`-prefixed percentage.

```python
def test_remainder_line_clamps_negative_rows_and_still_prints() -> None:
    """An over-counted top list prints a zero remainder, not a missing line."""
```
`rows=100`, `distinct=10`, `value_kind="top"`,
`values=[("a", 60), ("b", 60)]` — frequencies sum to 120. Assert the line
`"… 8 other values, 0 rows (0.0%)"` is present: the remainder line is
**printed**, not suppressed.

Import `_clamp0` in the new module only if asserting on it directly; the three
tests above go through the renderers, which is preferable.

## Commit

`fix(summarize): clamp cross-query count arithmetic at zero`

## Checks

`run_format_code`, `run_pylint_check`, `run_pytest_check` with
`extra_args: ["-n", "auto"]`, `run_mypy_check`, and `check_file_size` —
`test_render.py` sits 31 lines under the limit, so confirm this step left it
alone and that the new module is well under.

## Prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_2.md`. Implement step 2
> only: add `_clamp0` to `src/mcp_tools_sql/summarize/render.py` and use it at the
> three cross-query subtraction sites (`_render_block`, `render_triage`,
> `_render_values`). Write the three tests first, in the **new** module
> `tests/summarize/test_render_clamp.py` — do not add them to `test_render.py`,
> which is 719 lines against a CI-enforced 750-line limit. Do not touch
> `distinct_gated`,
> the gate rule, or the sample header — later steps own those. Run format, pylint,
> pytest (`-n auto`), mypy and check_file_size, then make one commit.
