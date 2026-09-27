# Step 3 — Floor at the two formatting sinks

Layer 3 of [summary.md](./summary.md). Makes the negative-slice primitive
unreachable from *any* caller, including the two that never pass through
`_cap_max_rows`.

## WHERE

- `src/mcp_tools_sql/formatting.py` — `format_rows` (~line 28) and
  `format_fanout_rows` (~line 62)
- `tests/test_formatting.py` — one test in `TestFormatRows`, one in the
  fan-out test class (~line 108)

## WHAT

Signatures unchanged:

```python
def format_rows(rows, max_rows: int = 100, truncation_hint: str = "") -> str: ...
def format_fanout_rows(rows, counts, errors, max_rows: int = 100,
                       truncation_hint: str = "") -> str: ...
```

Add `max_rows = max(max_rows, 1)` at the top of each body.

## HOW

Both functions need it: `format_fanout_rows` delegates to `format_rows` only
when `len(counts) <= 1 and not errors`; its multi-database branch slices
independently at `formatting.py:69`.

In `format_rows`, place the floor **after** the `if not rows:` early return so
the empty-result path is untouched. In `format_fanout_rows`, place it at the
very top, before the delegation branch (a re-floor inside `format_rows` is
harmless).

Four callers benefit, only two of which route through `_cap_max_rows`:
`execute_and_format`, the `fanout` closure, `read_databases`
(`schema_tools.py:95`, passes `len(rows)`) and `summarize/render.py:470`
(passes the `COLUMN_CAP` constant).

## ALGORITHM

```
format_rows(rows, max_rows, hint):
    if not rows: return "No results found."     # unchanged, runs first
    max_rows = max(max_rows, 1)
    ... unchanged from here
```

## DATA

Output shape is unchanged for every in-range `max_rows`. For `max_rows < 1`
with N rows, the result is the first row plus the footer
`Showing 1 of N rows.` — no rows leak past the cap and the footer no longer
prints a negative count.

## Tests (write first)

**1. `TestFormatRows`:**

```python
def test_negative_max_rows_floors_to_one(self) -> None:
    """A negative max_rows shows one row, not 'all but the last N'."""
    rows = [{"id": i} for i in range(5)]
    result = format_rows(rows, max_rows=-1)
    assert "Showing 1 of 5 rows." in result
    assert "3" not in result
```

`"3"` is the assertion that discriminates: the current `rows[:-1]` renders ids
0-3, so it fails pre-fix. (`"4"` would not — the buggy slice already drops the
last row.)

(Current behaviour, verified by probe: 4 of the 5 rows leak and the footer
reads `Showing -1 of 5 rows.`)

**2. Fan-out class** — must hit the *non-delegating* branch, so use two
databases in `counts`:

```python
def test_negative_max_rows_floors_to_one(self) -> None:
    rows = [{"id": i, "_database": "a" if i < 2 else "b"} for i in range(4)]
    counts = {"a": 2, "b": 2}
    result = format_fanout_rows(rows, counts, [], max_rows=-1)
    assert "Showing 1 of 4 rows." in result

    body = result.split("\n\nShowing")[0].splitlines()[2:]
    assert len(body) == 1
    assert body[0].split() == ["0", "a"]
```

The `body` assertions are what make a footer-only fix fail: `tabulate`'s
`simple` format emits a header line plus a separator line before the data rows,
so `splitlines()[2:]` is the rendered row list — three rows today, one after the
floor. An absence check (`"b" not in result`) would not work here: the footer
breakdown names every database.

Keep an existing-behaviour assertion in each (e.g. `max_rows=0` also floors to
1) only if it does not duplicate the above.

## Implementation

One line in each function, plus a sentence in each docstring's `max_rows`
argument description noting values below 1 are treated as 1.

## Checks

`run_format_code`, `run_pylint_check`, `run_pytest_check` (`["-n", "auto"]`),
`run_mypy_check` — all must pass. Existing `test_formatting.py` truncation
tests must stay green unchanged.

## Commit

```
fix(formatting): floor max_rows at 1 in the row and fan-out renderers
```

## LLM prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_3.md`, then implement
> step 3 only. Follow TDD: add the two tests first, watch them fail, then add
> the floor to both `format_rows` and `format_fanout_rows` at the positions
> described under HOW. Do not touch `query_helpers.py` or the verification
> package. Run `run_format_code`, `run_pylint_check`, `run_pytest_check` with
> `extra_args: ["-n", "auto"]` and `run_mypy_check`, then make exactly one
> commit.
