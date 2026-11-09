# Step 9 – Wire fan-out (`database="*"`) + architecture doc

## LLM prompt
Read `pr_info/steps/summary.md` (sections 4 and 5) and this file. Implement
step 9 only, test-first: move the fan-out path of `build_schema_body` onto
`collect` with one `Source` per target (shared display and counting budgets,
timeouts handled inside the batch loop), render with `render_limited`, remove
`format_fanout_rows`, and update `docs/architecture/architecture.md`. Run
pylint, pytest (`-n auto`), mypy, lint-imports, vulture; format; one commit.

## WHERE
- `src/mcp_tools_sql/query_helpers.py` – `build_schema_body.fanout`
- `src/mcp_tools_sql/formatting.py` – remove `format_fanout_rows` (and
  `format_rows`' `truncation_hint` parameter if it has no remaining callers;
  check with `find_references`)
- `docs/architecture/architecture.md`
- Tests: `tests/test_schema_tools_fanout_limits.py` (new); update fan-out
  assertions in `tests/test_schema_tools_multitarget.py` and remove the
  `format_fanout_rows` tests from `tests/test_formatting.py` (their behaviour is
  covered by `tests/test_formatting_limits.py`)

## WHAT
```python
# query_helpers.py
def _tagged_batches(
    registry: BackendRegistry,
    target: ResolvedTarget,
    sql: str,
    params: dict[str, Any] | None,
    counting: Deadline,
) -> Generator[list[dict[str, Any]], None, None]:
    """Yield the target's batches with a ``_database`` column added."""
```

## HOW
- `fanout`: build `sources = [Source(t.database, functools.partial(_tagged_batches, registry, t, resolved_sql, stripped or None)) for t in fan_targets]`.
- `collect(sources, max_rows=requested, limits=limits,
  counting_seconds=counting_time_limit(fan_targets[0].config.query_timeout_seconds),
  filter_rows=..., record_errors=True)`. The old outer `try/except Exception`
  per database goes away: `registry.backend_for` runs inside the generator, so
  its errors are recorded per database by `collect`.
- `render_limited(..., builtin=True, fanout=len(fan_targets) > 1)`. A
  connection with one database renders like a single target (replaces the old
  `len(counts) <= 1` shortcut, which lost the footer when counting ended early).
- `_tagged_batches` closes the inner generator in `finally`.
- Architecture doc:
  - fan-out paragraph (§5): replace "fetch-all, merge in config order, truncate
    at the end" with batched reads and shared display/counting budgets, `N+`
    and `not queried (...)` footer;
  - Key Modules table: add `result_limits.py`; `backends/base.py` row mentions
    `iter_readonly_batches`, `QueryTimeoutError`, `translate_timeout`;
  - Security / quality goals: statement and login timeouts, `[limits]`
    (output chars, cell chars, count rows).

## ALGORITHM
```
_tagged_batches(registry, target, sql, params, counting):
    inner = registry.backend_for(target).iter_readonly_batches(sql, params, counting=counting)
    try:
        for batch in inner:
            for row in batch: row["_database"] = target.database
            yield batch
    finally: inner.close()
```

## DATA
Fan-out text: merged table with `_database`, §5 message, `Matched: …` footer,
cell-cut line, per-database error lines.

## Tests (write first)
`tests/test_schema_tools_fanout_limits.py` (fake backends via
`tests.target_helpers.RecordingRegistry` / `make_target`; fakes override
`iter_readonly_batches` where they must raise mid-stream):
- (a) First database exhausts only the display budget (`max_rows=5`, 20 rows;
  second database 7 rows) → `Matched: sales 20, hr 7.`, footer present.
- (b) First database exhausts the counting budget (`max_count_rows=100`,
  150 rows) → `sales 100+`, later databases `not queried (limit reached)`,
  footer present (not single-database output).
- (c) A database times out after yielding rows → `N+`, its shown rows kept
  (`_database` value visible), later databases `not queried (stopped:
  statement timeout)`, footer present.
- (d) A database times out before any row → its error line
  `hr: Query aborted after 30 s (statement timeout).`, later databases not
  queried, footer present.
- Display and counting budgets are shared: total shown rows ≤ `max_rows` across
  databases; counted rows ≤ `max_count_rows` across databases.
- A non-timeout error in one database → its error line, other databases still
  counted.
