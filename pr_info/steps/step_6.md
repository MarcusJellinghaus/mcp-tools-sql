# Step 6 – `result_limits.collect`: filter, display budget, counting

## LLM prompt
Read `pr_info/steps/summary.md` (sections 3, 4 and 5) and this file. Implement
step 6 only, test-first: create `src/mcp_tools_sql/result_limits.py` with
`collect()`, the single collection path for single-target and fan-out reads,
plus the result dataclasses in `formatting.py`. Register the module in
`.importlinter` and `tach.toml`. Nothing calls `collect` yet. Run pylint,
pytest (`-n auto`), mypy, lint-imports; format; one commit.

## WHERE
- `src/mcp_tools_sql/result_limits.py` (new)
- `src/mcp_tools_sql/formatting.py` – `SourceCount`, `LimitedResult`, `StopReason`
- `.importlinter` – new layer line `mcp_tools_sql.result_limits` between
  `mcp_tools_sql.tool_builder` and
  `mcp_tools_sql.backends | mcp_tools_sql.formatting | mcp_tools_sql.tool_logging`
- `tach.toml` – new module `mcp_tools_sql.result_limits` (layer
  `tool_implementation`, depends on `backends`, `config`, `formatting`); add
  `{ path = "mcp_tools_sql.result_limits" }` to `query_helpers` `depends_on`
- Tests: `tests/test_result_limits.py` (new)

## WHAT
```python
# formatting.py
StopReason = Literal["end", "max_count", "counting", "timeout"]

@dataclass
class SourceCount:
    database: str
    matched: int = 0          # matched (post-filter) rows counted
    complete: bool = True     # False -> render as "N+"
    queried: bool = True      # False -> "not queried (...)"
    error: str = ""           # per-database error line
    timed_out: bool = False   # statement timeout before any matched row

@dataclass
class LimitedResult:
    rows: list[dict[str, str]]                         # display rows, cells stringified/cut
    sources: list[SourceCount]                         # config order
    display_limit: Literal["", "max_rows", "chars"] = ""
    stop: StopReason = "end"
    cells_cut: bool = False

    @property
    def total(self) -> int: ...      # sum of matched
    @property
    def complete(self) -> bool: ...  # stop == "end"

# result_limits.py
COUNTING_TIME_LIMIT_MAX: float = 5.0

@dataclass
class Source:
    database: str
    open: Callable[[Deadline], Generator[list[dict[str, Any]], None, None]]
    enforces_counting: bool = False  # backend interrupts at the counting deadline (SQLite)

def counting_time_limit(timeout_seconds: int) -> float: ...  # min(5.0, timeout / 2)

def cell_text(value: Any, max_cell_chars: int) -> tuple[str, bool]: ...

def collect(
    sources: list[Source],
    *,
    max_rows: int,
    limits: LimitsConfig,
    counting_seconds: float,
    filter_rows: Callable[[list[dict[str, Any]]], list[dict[str, Any]]] = _identity,
    record_errors: bool = False,
) -> LimitedResult: ...
```

## HOW
- `cell_text`: `None` → `""`, else `str(value)`; longer than `max_cell_chars` →
  `text[:max_cell_chars] + f"…[cut, {len(text):,} chars total]"`, flag `True`.
- Char budget (rendered with `tabulate(..., tablefmt="simple",
  disable_numparse=True)` in step 7): column width = max(len(header), longest
  line of any cell); line width = `sum(widths) + 2 * (ncols - 1)`; lines =
  2 (header + separator) + sum of row heights (row height = most lines in any
  cell). Admit a row only if `lines_after × (width_after + 1) ≤
  max_output_chars`, using the running maximum widths including the new row.
- The display set is complete when the first matched row is not admitted
  (`len(rows) == max_rows` → `"max_rows"`, budget refused → `"chars"`). At that
  moment set `counting.at = monotonic() + counting_seconds` (one shared
  `Deadline` for all sources).
- Always close each source generator in `finally` (`gen.close()`).
- `QueryTimeoutError` is caught inside the source loop: label it `"counting"`
  only if `src.enforces_counting` and `counting.at` is set and passed, else
  `"timeout"`. On backends that do not enforce the counting deadline (SQL
  Server checks it only between batches), a `QueryTimeoutError` is always the
  statement timeout. Mark the source
  incomplete; if it had no matched rows and the label is `"timeout"`, set
  `error=str(exc)`, `timed_out=True`. Stop counting.
- Any other exception: record `error=str(exc)` and continue with the next source
  when `record_errors`; otherwise re-raise (single-target behaviour today).
- Sources after a stop get `SourceCount(database, queried=False,
  complete=False)`.

## ALGORITHM
```
for src in sources:
    if stop != "end": append not-queried count; continue
    gen = src.open(counting)
    try: for batch in gen:
            for row in filter_rows(batch):
                if counted == limits.max_count_rows: stop = "max_count"; break   # row max_count+1 proves "more"
                counted += 1; src_count.matched += 1
                if not display_full: try admit row, else mark display_full + arm counting deadline
            if stop == "end" and display_full and monotonic() >= counting.at: stop = "counting"
            if stop != "end": src_count.complete = False; break
    except QueryTimeoutError / Exception: as in HOW
    finally: gen.close()
```

## DATA
`LimitedResult` as above. `rows` hold only display rows (≤ `max_rows`, within
the char budget); counted rows beyond them are discarded.

## Tests (write first)
`tests/test_result_limits.py`, with fake generator sources (and
`monkeypatch.setattr(result_limits.time, "monotonic", ...)` for clock tests):
- Reads at most `max_count_rows + 1` matched rows (instrumented source counts
  rows pulled); keeps only display rows; exact total below `max_count_rows`;
  `total == max_count_rows` and `complete is False` above it.
- With a filter, matches located beyond the first raw batch are found and
  counted.
- Counting time limit passed between batches → `stop == "counting"`, shown rows
  kept, `complete is False`.
- `QueryTimeoutError` during counting (after the counting deadline) →
  `"counting"` for a source with `enforces_counting=True`, `"timeout"` for
  one with `enforces_counting=False`; before the counting deadline →
  `"timeout"` either way; after some matched rows during display
  → rows kept, `stop == "timeout"`; before any matched row → `error`,
  `timed_out`.
- Fan-out: two sources share `max_rows` and `max_count_rows`; the second source
  is `queried=False` after the first exhausts the counting budget; exhausting
  only the display budget still counts the second source exactly; a non-timeout
  error with `record_errors=True` records the error and continues.
- Char budget: `tabulate(rows, headers="keys", tablefmt="simple",
  disable_numparse=True)` length ≤ `max_output_chars`, including a later row
  that widens an earlier non-last column and a multi-line cell; the first row
  wider than the budget → `rows == []`, `display_limit == "chars"`.
- `cell_text` cuts with the marker and reports the flag; `None` → `""`.
- `counting_time_limit(30) == 5.0`, `counting_time_limit(4) == 2.0`.
- SQLite integration (real `SQLiteBackend`, `query_timeout_seconds=2`, source
  opening `iter_readonly_batches`, `enforces_counting=True`): a counting phase that would outlast the
  counting time limit (1 s) is cut mid-batch → `stop == "counting"`; elapsed
  time < 2 s.
