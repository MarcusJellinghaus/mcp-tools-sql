# Issue #63 — `max_rows=-1` bypasses the row cap

## Problem

`max_rows` reaches two slice sites with no lower bound. A negative Python slice
(`rows[:-1]`) returns "all but the last |n|" rows instead of zero, so
`max_rows=-1` returns nearly the whole result set and defeats the
operator-configured display cap.

Two entry points:

1. **Caller argument** — `max_rows` is a plain `int` in the synthesized tool
   signature (`query_helpers.py:108`), and `_cap_max_rows`
   (`query_helpers.py:131-145`) only rejects values *above* `max_rows_hard`.
2. **Operator config** — `_cap_max_rows` clamps `requested` *down to*
   `config.max_rows_hard`, so `max_rows_hard = -1` triggers the same bug on
   every call with no caller argument involved. Nothing catches it today:
   `QueryConfig` has no bounds and `verification/queries.py:132` checks only
   `max_rows_default > 0`.

Measured on current code: `format_rows(5 rows, -1)` returns 4 rows with the
footer `Showing -1 of 5 rows.`

## Design changes

Three defensive layers plus a config check. None is redundant — the direct-call
paths that skip layer 1 and the `format_rows` callers that skip layer 2 both
exist and are exercised today.

| Layer | Where | Effect |
|---|---|---|
| 1. Schema constraint | `build_query_sig_params` | `max_rows < 1` is rejected by the MCP protocol before the tool body runs |
| 2. Runtime clamp | `_cap_max_rows` | Both `requested` and `hard` are floored at 1; a bad operator config is contained even if `verify` was never run |
| 3. Sink floor | `format_rows`, `format_fanout_rows` | The negative-slice primitive is unreachable from any caller |
| 4. Config check | `verification/queries.py` | `verify` reports `max_rows_hard <= 0` the same way it already reports `max_rows_default <= 0` |

Notable design points:

- **`Field(ge=1)` works through the synthesized signature.** `build_tool_fn`
  (`tool_builder.py:34`) attaches a fake `__signature__` to a `**kwargs`
  function; FastMCP's `func_metadata` reads it. Probe-confirmed: the published
  schema gains `"minimum": 1`, and both `-1` and `0` return `isError=True`
  before the body runs. One edit covers every configured query *and* every
  built-in schema tool, since both call `build_query_sig_params`.
- **The floor is needed in `format_fanout_rows` too.** It delegates to
  `format_rows` only when `len(counts) <= 1 and not errors`; the
  multi-database branch slices independently at `formatting.py:69`.
- **`_cap_max_rows` clamps, it does not raise.** Symmetric with the upper clamp
  already there and with `clamp_n` (`summarize/sql.py:562`). Raising would need
  a new exception type plus handlers in `execute_and_format` and `fanout`,
  neither of which has a generic exception tail.
- **A repaired `hard` is clamped silently.** When `max_rows_hard <= 0` the
  effective limit becomes 1, which the existing upper-clamp note already states
  (`capped at 1`). The operator-facing report for that misconfiguration is the
  new `verify` row, not a per-call note.
- **`max_rows=0` is invalid** (`ge=1`, not `ge=0`). A caller wanting a count
  without rows has `count_records`.
- **`QueryConfig` stays unconstrained.** `ge=1` on the pydantic model would fail
  config load with a raw pydantic error and make the existing
  `max_rows_default > 0` check dead code. `verify` stays the single friendly
  place config problems are reported.

Out of scope: summarize's `n` is already two-sided via `clamp_n`;
`count_records`, `validate_sql` and `read_databases` expose no limit parameter.

## Files created / modified

No new modules, packages or folders. `pr_info/steps/` is planning material only.

| File | Change | Step |
|---|---|---|
| `src/mcp_tools_sql/query_helpers.py` | `Field(ge=1)` on the `max_rows` annotation | 1 |
| `tests/test_query_tools.py` | Schema `minimum` assertion + MCP-level rejection test | 1 |
| `src/mcp_tools_sql/query_helpers.py` | Lower clamp in `_cap_max_rows` | 2 |
| `tests/test_query_tools.py` | Direct unit test of `_cap_max_rows` | 2 |
| `src/mcp_tools_sql/formatting.py` | Floor in `format_rows` and `format_fanout_rows` | 3 |
| `tests/test_formatting.py` | Negative-`max_rows` tests for both functions | 3 |
| `src/mcp_tools_sql/verification/queries.py` | `_positive_entry` helper + `<name>.max_rows_hard` row | 4 |
| `tests/verification/test_queries.py` | Test for the new row | 4 |
| `tests/cli/fixtures/verify_snapshot.txt` | Three new `max_rows_hard` rows in the golden snapshot | 4 |
| `docs/cli.md` | QUERIES section description + sample output | 4 |

## Steps

1. [step_1.md](./step_1.md) — schema constraint (`Field(ge=1)`)
2. [step_2.md](./step_2.md) — lower clamp in `_cap_max_rows`
3. [step_3.md](./step_3.md) — floor in the two formatting sinks
4. [step_4.md](./step_4.md) — `max_rows_hard > 0` verify check + docs

Each step is one commit: tests first, then implementation, then checks. The
steps are independent and can be committed in any order; the listed order goes
outside-in through the defensive layers.

## Checks per step

```
mcp__mcp-tools-py__run_format_code
mcp__mcp-tools-py__run_pylint_check
mcp__mcp-tools-py__run_pytest_check   extra_args: ["-n", "auto"]
mcp__mcp-tools-py__run_mypy_check
```
