# Step 2 — Lower clamp in `_cap_max_rows`

Layer 2 of [summary.md](./summary.md). Contains both a negative caller argument
arriving via a direct (non-MCP) call and an operator-configured
`max_rows_hard <= 0`.

## WHERE

- `src/mcp_tools_sql/query_helpers.py` — `_cap_max_rows` (lines 131-145)
- `tests/test_query_tools.py` — new sync test near the existing
  `test_execute_and_format_caps_max_rows_and_filters` (~line 33); add
  `_cap_max_rows` to the existing `from mcp_tools_sql.query_helpers import ...`

## WHAT

Signature and return type unchanged:

```python
def _cap_max_rows(config: QueryConfig, requested: int) -> tuple[int, str]: ...
```

## HOW

Both existing call sites (`execute_and_format` at line 170 and the `fanout`
closure at line 324) already unpack `(capped, note)` and append the note to
their output — no caller changes needed.

Update the docstring to state that both operands are floored at 1 and that a
repaired `hard` is silent (the resulting `capped at 1` upper-clamp note already
names the effective limit; `verify` owns the operator-facing report).

## ALGORITHM

```
hard = max(cast(int, config.max_rows_hard), 1)
if requested < 1:
    return 1, note("Requested max_rows={requested} is below the minimum 1; using 1.")
if requested > hard:
    return hard, note(...)          # unchanged
return requested, ""
```

Order matters: flooring `hard` first means a `max_rows_hard = -1` config with a
normal `requested` falls into the existing upper-clamp branch and reports
`capped at 1`.

## DATA

`(capped, note)` where `capped >= 1` always, and `note` is `""` or a string
starting with `"\n\n"` (matching the existing note convention so it appends
cleanly after the formatted table).

## Tests (write first)

One synchronous test — `_cap_max_rows` is a pure function, so no stub backend
and no async harness are needed:

```python
def test_cap_max_rows_floors_both_operands() -> None:
    """Negative/zero requested and a non-positive hard limit both floor to 1."""
    cfg = QueryConfig(sql="SELECT 1", max_rows_default=5, max_rows_hard=10)
    assert _cap_max_rows(cfg, -1)[0] == 1
    assert "below the minimum 1" in _cap_max_rows(cfg, -1)[1]
    assert _cap_max_rows(cfg, 0)[0] == 1

    bad_hard = QueryConfig(sql="SELECT 1", max_rows_default=5, max_rows_hard=-1)
    capped, note = _cap_max_rows(bad_hard, 5)
    assert capped == 1
    assert "capped at 1" in note
```

Also assert the unchanged happy path still holds (`_cap_max_rows(cfg, 3) ==
(3, "")`) so the floor cannot silently swallow a valid request.

## Implementation

Rewrite the body of `_cap_max_rows` per the algorithm above and update its
docstring.

## Checks

`run_format_code`, `run_pylint_check`, `run_pytest_check` (`["-n", "auto"]`),
`run_mypy_check` — all must pass. The existing clamp tests
(`test_query_tools.py:33`, `test_query_tools.py:320`,
`test_schema_tools.py:337`) must stay green unchanged.

## Commit

```
fix(query): floor max_rows and max_rows_hard at 1 in the cap helper
```

## LLM prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_2.md`, then implement
> step 2 only. Follow TDD: add the synchronous `_cap_max_rows` test first,
> watch it fail, then apply the two-operand floor described in the ALGORITHM
> section and update the docstring. Do not change the note text of the existing
> upper clamp, and do not touch `formatting.py` or the verification package.
> Run `run_format_code`, `run_pylint_check`, `run_pytest_check` with
> `extra_args: ["-n", "auto"]` and `run_mypy_check`, then make exactly one
> commit.
