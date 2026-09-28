# Step 5 — Per-variant `read_only` rows in `verify`

Read [summary.md](./summary.md) first, especially *"Verify gains a static,
per-variant check"*. Depends on step 2 (the shared helper) and step 4 (the label
width). This is decisions 7, 11 and 12.

## WHERE

- `src/mcp_tools_sql/verification/_helpers.py` — `make_warn_entry`
- `src/mcp_tools_sql/verification/queries.py` — the rows
- `tests/verification/test_queries.py`
- `tests/cli/fixtures/verify_snapshot.txt` (regenerated again)

## WHAT

```python
# verification/_helpers.py
def make_warn_entry(value: str, error: str = "") -> dict[str, Any]:
    """Build a WARN entry that does not affect the exit code."""
```

It bakes in `ok=True` — exactly the footgun the summary's constraint section
warns about — and mirrors how `make_skipped_entry` post-sets `warn`. Used here
and again in step 6.

In `verify_one_query`, add `read_only` rows in three shapes:

| Situation | Row key | Entry |
|-----------|---------|-------|
| Pin resolved, variant dialect maps | `<name>.read_only[<backend>]` | `ok=True, value="read-only"` or `ok=False, value="failed", error=<rejection>` |
| Pin resolved, variant name unmappable (decision 11) | `<name>.read_only[<backend>]` | `make_warn_entry("(unknown backend)", <ValueError text>)` |
| Pin unresolvable (decision 12) | `<name>.read_only` — **un-suffixed** | `ok=False, value="(skipped)", error=<pin error>` |

## HOW

- Import `read_only_rejection` from `query_helpers` (the module already imports
  `extract_sql_params` from there) and `to_dialect` from `backends.base` (already
  imports `DatabaseBackend` from there).
- **Variant set and order.** The set is `{target.backend_name} | set(qcfg.backends)`
  (decision 7). Iterate **pinned backend first, then the remaining declared
  `qcfg.backends` keys in config order** — deterministic without sorting, which
  the byte-identical snapshot needs.
- Resolve SQL **per variant** with `qcfg.resolve_sql(variant)`. A variant exists
  precisely because its SQL differs; reusing the pinned SQL would defeat the row.
- `to_dialect` raises `ValueError` outside `sqlite`/`mssql`/`pyodbc`. Catch it per
  variant and emit the warn row — a `postgresql` key or a typo is dead config the
  operator should see, but failing `verify` over SQL that never executes would be
  wrong, and skipping silently would hide it.
- **Row position:** immediately after `<name>.sql`, before `<name>.params`. Dict
  insertion order is the print order.
- The unresolvable-pin early return (`queries.py:100-110`) gains its single
  un-suffixed row. No `[<backend>]` suffix can be formed there — `target` does not
  exist, which is what failed. (Emitting one row per declared `backends` key
  instead was rejected: a query with no overrides would emit zero rows and drop
  out of the output silently.)
- Update `verify_one_query`'s docstring — it says "Three-row dict" and lists the
  keys. It is now four-plus rows.
- `verify_queries`' `overall_ok` already reads `entry["ok"] or entry.get("warn", False)`,
  and the CLI checks `warn` before `ok`, so a decision-11 warn row cannot flip the
  exit code. Nothing to change there.

## ALGORITHM

```
variants = [target.backend_name] + [k for k in qcfg.backends if k != target.backend_name]
for variant in variants:
    try:
        dialect = to_dialect(variant)
    except ValueError as exc:
        result[f"{name}.read_only[{variant}]"] = make_warn_entry("(unknown backend)", str(exc))
        continue
    rejection = read_only_rejection(qcfg.resolve_sql(variant), dialect)
    result[f"{name}.read_only[{variant}]"] = make_entry(
        ok=rejection is None,
        value="read-only" if rejection is None else "failed",
        error=rejection or "",
    )
```

## DATA

Standard verifier entries (`ok`, `value`, `error`, `install_hint`, plus `warn`
where set). No `install_hint` — there is nothing to install.

Note this row needs no database but still inherits the connection skip
(`orchestrator.py:203` only appends `QUERIES` when `default_ok`). Consistent with
the existing static `params` / `max_rows_default` rows; out of scope to change.

## TESTS (write first)

`tests/verification/test_queries.py` — the existing fixtures use `Mock`
backends, which is fine: these rows touch no backend.

- A clean `SELECT` query → one `<name>.read_only[sqlite]` row, `ok=True`.
- A `DELETE` query → `ok=False`, and the rejection text lands in `error`.
- A query with `[queries.x.backends.mssql]` whose override is a `DELETE` while
  the pinned sqlite SQL is a clean `SELECT` → the `[sqlite]` row passes and the
  `[mssql]` row fails. **This is the decision-7 test**; without it the whole
  per-variant design is untested.
- A `backends.postgresql` key → a `warn` row, and `overall_ok` stays `True`.
- An unresolvable pin → exactly one un-suffixed `<name>.read_only` row, present
  alongside the existing `(skipped)` / `failed` rows.
- Row order: `read_only` rows sit between `.sql` and `.params`.

Then regenerate `tests/cli/fixtures/verify_snapshot.txt` from actual output. The
three snapshot queries gain one `read_only[sqlite]` row each. `bad_sql`'s SQL is
`SELECT * FROMX badtable` — do not predict its verdict, read it from the
regenerated output and sanity-check that the value makes sense.

## LLM PROMPT

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_5.md`. Steps 1–4 are
> done.
>
> Implement step 5 test-first: add the per-variant `read_only` row tests to
> `tests/verification/test_queries.py` — including the decision-7 case where a
> `backends.mssql` override is a `DELETE` while the pinned sqlite SQL is a clean
> `SELECT` — watch them fail, then add `make_warn_entry` to
> `src/mcp_tools_sql/verification/_helpers.py` and the rows to `verify_one_query`
> in `src/mcp_tools_sql/verification/queries.py`.
>
> Reuse `read_only_rejection` from step 2; do not reimplement the gate logic —
> the row exists to predict what the server does at startup, so the two must share
> one implementation.
>
> Then regenerate `tests/cli/fixtures/verify_snapshot.txt` from actual output
> (never hand-pad) and update `verify_one_query`'s "Three-row dict" docstring.
>
> Then run `run_format_code`, `run_pylint_check`, `run_pytest_check` with
> `extra_args: ["-n", "auto"]`, `run_mypy_check`, `run_tach_check` and
> `run_lint_imports_check`. All must pass. Commit as one commit.
