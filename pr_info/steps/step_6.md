# Step 6 — `:memory:` warning on the sqlite `path` row

Read [summary.md](./summary.md) first, especially the `ok=True` constraint — it is
not a style preference, it is load-bearing. This is decisions 5, 8 and 14.

Depends on step 5 only for `make_warn_entry`.

## WHERE

- `src/mcp_tools_sql/verification/connection.py` (the sqlite branch at `:131-134`)
- `tests/verification/test_connection.py`

## WHAT

The sqlite `path` row becomes three-way:

```python
if connection.backend == "sqlite":
    if connection.path == ":memory:":
        result["path"] = make_warn_entry(":memory:", _MEMORY_PATH_HINT)
    else:
        result["path"] = _required_str_entry(
            connection.path, required_error="path must be set for sqlite"
        )
```

with a module-level hint constant explaining the failure mode.

## HOW

- **`ok=True, warn=True` is mandatory.** `verify_connection`'s `overall_ok` and
  `_verify_connections` (`orchestrator.py:159-161`) both read bare `entry["ok"]`
  with no warn tolerance. That value becomes `pair_ok` → `reachable` →
  `default_ok`, and `default_ok=False` skips the whole QUERIES/UPDATES block
  (`orchestrator.py:203`). An `ok=False` path row would silently suppress the
  `read_only` rows step 5 just added. `make_warn_entry` bakes this in.
- Why the row is here and not in `verification/queries.py`: it is a
  per-connection fact, so putting it in the queries verifier would repeat it once
  per query (decision 8).
- The hint text should say what actually goes wrong: a fresh connection to
  `:memory:` is a **new, empty** database, so read paths silently return zero rows
  while `updates.*` still writes to the real persistent connection. After step 3
  this affects configured queries and the schema bodies, not just
  `count_records` / `summarize_columns`. The CLI prints a warn row's `error`
  field, so the hint is visible.
- This is a warning, not a rejection, and not a backend special-case beyond the
  branch that already exists (decision 5).
- No snapshot impact: the fixture covers QUERIES + UPDATES only, and this row is
  in CONNECTION.

## ALGORITHM

None beyond the branch above.

## DATA

`{"ok": True, "value": ":memory:", "error": <hint>, "install_hint": "", "warn": True}`
— renders as `[WARN]` and increments the warning count, never the error count.

## TESTS (write first)

`tests/verification/test_connection.py`:

- `path = ":memory:"` → the `path` row has `ok is True` **and** `warn is True`.
  Assert both explicitly; `ok is True` is the regression guard for the
  suppression bug described above.
- A normal file path → unchanged row, no `warn` key set.
- An empty path → still the existing `ok=False` "path must be set" row.
- One test that the pair's `overall_ok` stays `True` with a `:memory:` path,
  given every other row passes. That is the assertion that actually protects the
  QUERIES block.

Decision 14 has no other test fallout: the only `:memory:` use that could reach a
`path` row is `tests/verification/conftest.py:59`, whose targets never go through
`verify_connection`. Confirm that rather than assuming it.

## LLM PROMPT

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_6.md`. Steps 1–5 are
> done, so `make_warn_entry` exists.
>
> Implement step 6 test-first: add the `:memory:` row tests to
> `tests/verification/test_connection.py` — asserting `ok is True` and
> `warn is True`, plus that the pair's `overall_ok` stays `True` — watch them
> fail, then add the `:memory:` branch to the sqlite `path` row in
> `src/mcp_tools_sql/verification/connection.py`.
>
> The row must be `ok=True, warn=True`: an `ok=False` path row propagates to
> `default_ok` and silently suppresses the whole QUERIES section, including the
> `read_only` rows from step 5.
>
> Then run `run_format_code`, `run_pylint_check`, `run_pytest_check` with
> `extra_args: ["-n", "auto"]` and `run_mypy_check`. All must pass. Commit as one
> commit.
