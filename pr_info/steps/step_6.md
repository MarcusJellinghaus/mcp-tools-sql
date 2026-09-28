# Step 6 — `inconsistent_counts_note()` and footer order

Step 2 stopped the impossible numbers from printing. This step says so when it
happens: a clamped remainder line that reads `0 rows (0.0%)`, or a remainder line
that vanished because `rem_vals` went non-positive, is otherwise indistinguishable
from a correct profile.

## WHERE

- `src/mcp_tools_sql/summarize/render.py` — new `inconsistent_counts_note()`,
  beside `distinct_gate_note()`.
- `src/mcp_tools_sql/summarize/tools.py` — new `_counts_inconsistent`; the footer
  list in `_run`.
- `tests/summarize/test_tools.py` — the five conditions plus the clean case.
- `tests/summarize/test_tools_query_source.py` — the footer-order case.

## WHAT

**`render.py`:**

```python
def inconsistent_counts_note() -> str:
    """Footer note for a profile whose counts disagree with each other.

    The pipeline runs its count, scalar and value-list queries separately with no
    snapshot, so a concurrent write can leave one query's total below another
    query's part. ``render.py`` clamps the arithmetic at zero
    (:func:`_clamp0`); this note is what tells the reader that a printed zero
    remainder -- or an absent remainder line -- is that skew rather than the
    data.

    Returns:
        The inconsistent-counts footer note.
    """
```

Suggested text, one sentence plus the consequence:

```
Counts from separate queries disagree: the source changed while it was being
profiled, so some totals below are approximate.
```

(one line; the break is this document's wrapping).

**`tools.py`** — a pure predicate, not an accumulator threaded through the profile
loop. `ColumnProfile` already holds every value the five conditions need:

```python
# Stats counted by the scalar query but percentaged against ``rows`` from the
# count query, so the same skew pushes them over their own denominator.
_ROW_BOUNDED_STATS = ("zero", "neg", "empty", "true", "false")


def _counts_inconsistent(p: ColumnProfile) -> bool:
    """Whether a profile's counts disagree across the queries that produced them.

    Read before rendering, once per profiled column; ``_run`` appends
    :func:`inconsistent_counts_note` when any column answers ``True``. Pure --
    it takes the assembled profile and returns a bool, so no flag travels out of
    a renderer and the loop keeps no accumulator.

    Returns:
        ``True`` when at least one count exceeds the total it is part of.
    """
```

The five conditions, all cheap integer comparisons:

1. `p.non_null > p.rows` — the null count would go negative.
2. `p.value_kind == "top"` and `sum(freq) > p.rows` — the shown frequencies
   exceed the total, so the row remainder would go negative.
3. `p.value_kind == "top"` and `p.distinct is not None` and
   `p.distinct < len([v for v, _ in p.values if v is not None])` — **strictly**
   less. `rem_vals == 0` is legitimate: the list covered every distinct value.
   This one has no clamp of its own — `if rem_vals > 0` already absorbs it by
   dropping the whole remainder line, which is why it needs the note most: the
   evidence is a line that is simply not there.
4. `p.value_kind == "sample"` and `p.distinct is not None` and
   `len(p.values) > p.distinct`. Skipped when `distinct is None` — the comparison
   is undefined.
5. any `p.stats.get(k) or 0` over `_ROW_BOUNDED_STATS` exceeding `p.rows`.
   Detection only: no new clamps, and the resulting percentages print uncapped
   rather than capped at 100% — consistent with step 2 printing the clamped
   remainder line rather than suppressing it. `false` prints as a bare count in
   `_boolean_lines` with no percentage, so it is caught on the count alone.
   `… or 0` keeps the check total against an absent key and against a NULL
   aggregate.

Guard 2-4 on `p.values` being non-empty before indexing.

**The footer**, in `_run`, in exactly this order:

```python
footer: list[str] = []
if not include_distinct:
    footer.append(distinct_gate_note())
if any(_counts_inconsistent(p) for p in profiles):
    footer.append(inconsistent_counts_note())
footer.extend(source.notes)
if clamp_note:
    footer.append(clamp_note)
```

One note per call regardless of how many columns skew; the note names no columns.
`clamp_note` stays last, preserving today's placement — an existing test pins the
output ending with `SQLITE_PROBE_TYPE_LIMITS_NOTE`, which is a `source.notes`
entry.

## HOW

Import `inconsistent_counts_note` from `mcp_tools_sql.summarize.render` alongside
`distinct_gate_note`. `_counts_inconsistent` is a module-level private function in
`tools.py`, beside `_split_stats` — importable by tests without a backend.

## ALGORITHM

```
_counts_inconsistent(p):
    if p.non_null > p.rows: return True
    if any((p.stats.get(k) or 0) > p.rows for k in _ROW_BOUNDED_STATS): return True
    if p.values:
        if p.value_kind == "top":
            if sum(freqs) > p.rows: return True
            if p.distinct is not None and p.distinct < count_nonnull_shown: return True
        elif p.distinct is not None and len(p.values) > p.distinct: return True
    return False
```

## DATA

`_counts_inconsistent(p: ColumnProfile) -> bool`;
`inconsistent_counts_note() -> str`; `_ROW_BOUNDED_STATS: tuple[str, ...]`.

## TDD

**Five condition tests plus one clean case**, in `tests/summarize/test_tools.py`,
as direct calls to `_counts_inconsistent` with hand-built `ColumnProfile`s — the
style `test_render.py` already uses throughout. No MagicMock backend needed, which
is the point of making the predicate pure.

```python
def test_counts_inconsistent_non_null_over_rows() -> None:
def test_counts_inconsistent_top_frequencies_over_rows() -> None:
def test_counts_inconsistent_distinct_below_shown_values() -> None:
def test_counts_inconsistent_sample_longer_than_distinct() -> None:
def test_counts_inconsistent_row_bounded_stat_over_rows() -> None:
def test_counts_consistent_normal_profile_is_clean() -> None:
```

Two boundary cases that must answer `False`, or the note fires on ordinary output:

- `p.distinct == shown_nonnull_distinct` (condition 3 is strict) — a top list that
  covered every distinct value.
- `p.value_kind == "sample"` with `p.distinct is None` — condition 4 is skipped,
  not evaluated.

Parametrise the fifth over all five stat names so `false` is covered even though
it carries no percentage.

**One pipeline test**, same file: the note reaches the footer when the backend
returns `nonnull` above the row count, and does not appear for a normal profile.
Reuse the `_gate_backend` fake shape, returning `c0__nonnull` greater than
`row_count`.

**One footer-order test**, in `tests/summarize/test_tools_query_source.py`, beside
`test_wide_source_renders_triage_with_notes_after_footers`. Neither existing
pinning test would catch a regression in the order: test_tools.py:267 has an empty
`source.notes`, and test_tools_query_source.py:406 has no clamp note. The new case
must carry **both** — a `sql=` source (which contributes `TYPES_PROBED_NOTE` and
`SQLITE_PROBE_TYPE_LIMITS_NOTE`) called with `n=999` (which contributes the clamp
note):

```python
async def test_footer_order_source_notes_then_clamp_note() -> None:
    """source.notes precede the clamp note, which stays last."""
    ...
    out = await call_summarize(client, sql="SELECT qty FROM profile_me", n=999)
    assert out.index(TYPES_PROBED_NOTE) < out.index("Requested n=999")
    assert out.endswith("Requested n=999 exceeds the maximum 50; using 50.")
```

Add it as a **new** test — do not fold it into
`test_wide_source_renders_triage_with_notes_after_footers`, whose
`endswith(SQLITE_PROBE_TYPE_LIMITS_NOTE)` assertion is exactly the placement that
must keep holding.

## Commit

`feat(summarize): note in the footer when cross-query counts disagree`

## Checks

`run_format_code`, `run_pylint_check`, `run_pytest_check` with
`extra_args: ["-n", "auto"]`, `run_mypy_check`, `run_vulture_check` (two new
module-level functions), and `check_file_size` — the last step of the change, so
confirm `render.py` and `tools.py` are still under 750 lines.

## Prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_6.md`. Implement step 6
> only: add `inconsistent_counts_note()` to `src/mcp_tools_sql/summarize/render.py`
> and the pure predicate `_counts_inconsistent(profile)` to `tools.py`, then wire
> the footer in the order `distinct_gate_note`, `inconsistent_counts_note`,
> `source.notes`, `clamp_note`. Write the six predicate tests, the two boundary
> cases, the pipeline test and the footer-order test first. Add no new clamps —
> condition 5 is detection only and its percentages print uncapped. Run format,
> pylint, pytest (`-n auto`), mypy, vulture and check_file_size, then make one
> commit.
