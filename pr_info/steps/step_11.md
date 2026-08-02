# Step 11 — schema_tools: `database="*"` fan-out + `_database` + footer

See `pr_info/steps/summary.md` → "Tool surface" and simplification A
(fetch-all → merge → truncate; exact per-database counts for free).

## WHERE
- `src/mcp_tools_sql/query_helpers.py` (extend `build_target_params`, `build_schema_body`)
- `src/mcp_tools_sql/formatting.py` (add `format_fanout_rows`)
- Tests: `tests/test_schema_tools.py`, `tests/test_formatting.py`

## WHAT
- `build_target_params`: gains a keyword-only `star: bool = False` parameter;
  when `star=True`, `"*"` is appended to the `database` enum (fan-out sentinel).
  The `schema_tools` caller passes `star=True`. Introducing the flag here (rather
  than later) means non-fan-out callers (`validate_sql` / `count_records`,
  Step 12) simply take the `star=False` default and never see `"*"` — no
  signature rework or caller patching in Step 12.
- `build_schema_body`: when `database == "*"`, execute against **all** databases of
  the resolved connection, tag each row with a `_database` column, merge in config
  order, cap the merged total at `max_rows`, and render a per-database footer.
  A per-target failure is reported **inline**, not raised.
- `format_fanout_rows(rows, counts, errors, max_rows, truncation_hint) -> str`.

## HOW
- `_database` column is added **only** on the fan-out path (single-target output
  unchanged from Step 10).
- Targets: `targets.for_connection(connection or file_default)`. All share one
  connection → one `backend_name` → `resolve_sql`/`to_dialect` resolved once.
- `format_fanout_rows`: when `len(counts) <= 1` and no errors, delegate to
  `format_rows` for byte-identical single output; otherwise render table, then a
  truncation footer `"Showing N of T rows. Matched: db1 a, db2 b. <hint>"`, then
  one line per errored database.

## ALGORITHM (fan-out branch)
```
rows, counts, errors = [], {}, []
sql = config.resolve_sql(conn_backend_name)
for t in targets.for_connection(conn):
    try:
        r = apply_filter(registry.backend_for(t).execute_query(sql, params), col, pat)
        for row in r: row["_database"] = t.database
        counts[t.database] = len(r); rows += r        # exact count, free
    except Exception as e: errors.append((t.database, str(e)))
return format_fanout_rows(rows, counts, errors, requested, hint)
```

## DATA
Merged `list[dict]` with a `_database` key (config order). Footer counts are exact
because each target is fully fetched. Truncation caps the merged list at the end.

## TESTS (write first, fake registry + fake backends)
- `database="*"` merges rows from two fake databases with a `_database` column in
  config order.
- Per-database footer counts are exact; merged total capped at `max_rows`; footer
  appears only on truncation.
- One target raising → its error rendered inline, other target's rows still shown.
- `name_filter` under fan-out filters per target before merge (matches beyond the
  cap are not silently dropped — filter then cap).
- `format_fanout_rows` with one db and no errors == `format_rows` output.

## LLM PROMPT
> Implement Step 11 from `pr_info/steps/step_11.md` (context in
> `pr_info/steps/summary.md`). Extend `build_target_params` to add `"*"` to the
> `database` enum and `build_schema_body` with a fan-out branch that fetches all
> databases of the connection, tags rows with `_database`, merges in config order,
> caps the merged total at `max_rows`, and renders per-database footer counts plus
> inline per-target errors via a new `format_fanout_rows` in `formatting.py`. Use
> the fetch-all/merge/truncate strategy (no SQL TOP/LIMIT). `_database` appears
> only under fan-out; single-target output stays byte-identical. Write tests first
> (fake registry). Run pylint, pytest (`-n auto` + unit markers), mypy,
> lint-imports/tach; all green. One commit.
