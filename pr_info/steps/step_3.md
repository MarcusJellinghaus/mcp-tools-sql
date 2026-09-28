# Step 3 — Switch the tool-facing read paths to `execute_readonly_query`

Read [summary.md](./summary.md) first, especially *"Two layers, honestly
labelled"* and *"Cost accepted"*.

Independent of steps 1–2; this is the DB-enforced backstop (decision 4).

## WHERE

- `src/mcp_tools_sql/query_helpers.py` — two call sites
- `tests/test_query_tools.py` — `_StubBackend` + two `monkeypatch` spies
- `tests/test_schema_tools_multitarget.py` — one fake
- `tests/backends/test_registry.py` — one fake (verify only; it already defines
  the method)
- `tests/cli/test_verify.py` — one `MagicMock` side effect

## WHAT

Two one-line changes:

1. `execute_and_format` (`query_helpers.py:180`):
   `backend.execute_query(...)` → `backend.execute_readonly_query(...)`
2. The `database="*"` fan-out in `build_schema_body` (`query_helpers.py:339-343`):
   `registry.backend_for(target).execute_query(...)` →
   `...execute_readonly_query(...)`

Both are already on the `DatabaseBackend` ABC as abstract methods, so no
interface change.

## HOW

- `execute_and_format` is the shared tail for **configured queries and the pinned
  schema bodies**, so one edit covers two of the three paths in decision 4. The
  fan-out is the third. No path branching in the shared helper (decision 4).
- **Do not touch** the internal `verify` probes (decision 9): the `SELECT 1`
  liveness check at `verification/connection.py:203` and the column introspection
  at `verification/updates.py:29,37`. Those are server-authored, so the gate has
  nothing to add and the extra SQLite connection is pure cost.
- **Do not add a default `execute_readonly_query`** to the ABC that delegates to
  `execute_query`. It would make the fake updates unnecessary and silently hand
  every future backend a fake read-only guarantee.
- Add to `execute_and_format`'s docstring that it executes read-only, and that on
  SQLite this opens a fresh `PRAGMA query_only = ON` connection per call — under
  `database="*"`, one per target per call. Accepted cost, worth recording where
  the next reader will look.

## ALGORITHM

None — a method-name substitution at two sites.

## DATA

Unchanged: `list[dict[str, Any]]` rows in, formatted `str` out. Both backends'
`execute_readonly_query` return the same shape as `execute_query`.

## TESTS (write first)

Assert the *method*, since the return shape is identical and a silent revert
would otherwise pass:

- Configured-query path: a stub backend whose `execute_query` raises
  `AssertionError` and whose `execute_readonly_query` returns rows. A tool call
  must succeed.
- Fan-out path: same stub shape, through `build_schema_body` with
  `database="*"`. **"The call succeeded" is not a sufficient assertion here** —
  the fan-out wraps each target's execute in `except Exception`
  (`query_helpers.py:350`) and folds the failure into an inline per-target error
  string, so a still-on-`execute_query` implementation returns a formatted
  result instead of raising and the test would false-pass. Assert both: the
  expected rows are present in the output, **and** no inline per-target error
  text appears (no `AssertionError` / error-section marker for any target).

Fake updates:

- `tests/test_query_tools.py:37` `_StubBackend` — add
  `execute_readonly_query` (delegate to `execute_query`, or return the same
  rows).
- `tests/test_query_tools.py:363` and `:509` — the `monkeypatch` spies currently
  target `execute_query`; retarget them.
- `tests/test_schema_tools_multitarget.py:392` — the fake's
  `execute_readonly_query` raises `NotImplementedError`; make it delegate to
  `execute_query` so the recorded-call assertions keep working.
- `tests/backends/test_registry.py:48` — already defines the method; confirm it
  returns something usable and leave it otherwise.
- `tests/cli/test_verify.py:315` — sets `execute_query.side_effect`. That test
  exercises the `SELECT 1` probe, which decision 9 leaves on `execute_query`, so
  it should need **no** change. Verify that; if it fails, the wrong call site was
  switched.
- `tests/verification/*` fakes are `Mock`s and need nothing.

## LLM PROMPT

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_3.md`.
>
> Implement step 3 test-first: add the tests asserting that the configured-query
> path and the `database="*"` fan-out call `execute_readonly_query` (and never
> `execute_query`), watch them fail, then make the two one-line switches in
> `src/mcp_tools_sql/query_helpers.py` and update the four test fakes listed in
> the step.
>
> Leave the internal `verify` probes on `execute_query` per decision 9, and do
> not add a delegating default to the `DatabaseBackend` ABC.
>
> Then run `run_format_code`, `run_pylint_check`, `run_pytest_check` with
> `extra_args: ["-n", "auto"]` and `run_mypy_check`. All must pass. Commit as one
> commit.
