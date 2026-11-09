# Step 7 – `render_limited`: truncation messages and rendering

## LLM prompt
Read `pr_info/steps/summary.md` (section 5) and this file. Implement step 7
only, test-first: add `render_limited()` to `formatting.py`, which turns a
`LimitedResult` into the table plus the issue's §5 truncation message,
fan-out footer, cell-cut line, error lines and timeout hint. Pure function; no
tool uses it yet. Run pylint, pytest (`-n auto`), mypy; format; one commit.

## WHERE
- `src/mcp_tools_sql/formatting.py`
- Tests: `tests/test_formatting_limits.py` (new)

## WHAT
```python
def render_limited(
    result: LimitedResult,
    *,
    max_rows: int,            # effective (capped) max_rows
    max_rows_hard: int,       # effective hard limit of the tool
    has_sql_params: bool,     # resolved SQL has :placeholders (sql_params non-empty)
    filter_column: str,       # "" when the tool has no *_filter
    builtin: bool,            # built-in schema tool vs configured query_* tool
    fanout: bool,             # more than one target
    max_output_chars: int,
    max_cell_chars: int,
) -> str: ...

def _truncation_message(...) -> str: ...
def _next_steps(...) -> list[str]: ...
def _matched_footer(result: LimitedResult) -> str: ...
```

## HOW
- Single target with `sources[0].timed_out`: return
  `sources[0].error` + (` Use more selective parameters.` if `has_sql_params`).
- Table: `tabulate(result.rows, headers="keys", tablefmt="simple",
  disable_numparse=True)`, or `No results found.` when there are no rows.
- Truncated = `len(rows) < total` or not `complete`. Then add the message.
- Fan-out footer when `fanout` and (truncated or any source incomplete / not
  queried): `Matched: sales 4,213, hr 37,000+, fin not queried (limit reached).`
  Not-queried label: `(stopped: statement timeout)` when `stop == "timeout"`,
  else `(limit reached)`. Sources with an `error` are left out of `Matched:`
  and get their own `db: message` line (as today).
- Cells cut: `Long values were cut at {max_cell_chars} chars.`
- Join blocks with blank lines: table, message, footer, cell line, error lines.
- Numbers use thousands separators (`f"{n:,}"`); `N+` when incomplete.

## ALGORITHM
```
reasons: "max_rows={max_rows} reached" | "{max_output_chars:,}-char output limit reached";
         plus "counting stopped" (stop in max_count/counting) | "stopped: statement timeout"
head: first row too wide -> "the first row is wider than the {limit:,}-char output limit; showing 0 of {total} rows."
      else "showing {len(rows)} of {total} rows ({'; '.join(reasons)})."
param phrase: has_sql_params -> "refine parameters" (max_rows) / "filter with parameters" (chars);
              elif filter_column -> f"narrow with {filter_column}_filter"; else none
max_rows hit: steps = ["increase max_rows (hard limit H)"] if max_rows < H, + param phrase -> "To see more rows: a or b."
              no steps -> configured: "Operator: raise max_rows_hard in the query config."; builtin: nothing
chars hit:   param phrase -> "To see different or fewer rows: {phrase}."; else "Operator: raise [limits] max_output_chars."
             first row too wide -> configured: "Operator: select fewer columns in the configured SQL or raise [limits] max_output_chars."
                                   builtin: "Operator: raise [limits] max_output_chars."
stop == "timeout" and has_sql_params -> extra line "Use more selective parameters."
message = "[Output truncated: " + head + "".join("\n" + line for line in steps) + "]"
```

## DATA
Returns the final tool text (without the `_cap_max_rows` note, which callers
append).

## Tests (write first)
`tests/test_formatting_limits.py`, parametrised over hand-built
`LimitedResult`s:
- `max_rows` hit with exact total: `showing 100 of 4,213 rows (max_rows=100 reached)`
  and `increase max_rows (hard limit 500) or refine parameters`.
- `max_rows == max_rows_hard`: only `refine parameters`.
- Built-in, no params, no filter, `max_rows` hit: states the limit, no next step,
  no `max_rows_hard` mention.
- Configured query, no params, no filter, `max_rows == hard`:
  `Operator: raise max_rows_hard in the query config.`
- Filter column, no `sql_params`: `narrow with name_filter` (never a parameter
  phrase).
- Chars hit with params: `80,000-char output limit reached` +
  `To see different or fewer rows: filter with parameters.`; without params or
  filter: `Operator: raise [limits] max_output_chars.`
- Counting stopped: `of 37,000+ rows (... counting stopped)`.
- Timeout after rows: `showing 5 of 5+ rows (stopped: statement timeout)`,
  plus `Use more selective parameters.` only when `has_sql_params`.
- Single-target timeout before any row: exact
  `Query aborted after 30 s (statement timeout).` (no params) / with hint.
- First row too wide: configured vs built-in operator lines.
- Cells cut line present.
- Fan-out footer: exact counts, `N+`, `not queried (limit reached)`,
  `not queried (stopped: statement timeout)`, error lines; no footer when
  nothing is truncated and all sources are complete.
