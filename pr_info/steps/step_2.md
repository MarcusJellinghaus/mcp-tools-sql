# Step 2 — Dialect-first parse-error verdict in `basic_preflight`

> Read `pr_info/steps/summary.md` first. This step implements item 4 of the
> issue. Independent of Step 1 (different function, different message). One commit.

## TDD order

1. **Tests first.** Update the four assertions that pin the old prefix so they
   expect the new dialect-first form (they fail against the current code).
2. **Implementation.** Change the one f-string in `basic_preflight`.
3. Run all gates green.

## WHERE

- `src/mcp_tools_sql/utils/sql_placeholders.py` — `basic_preflight`, the
  `except ParseError` branch (line ~335).
- `tests/test_count_tools.py` (line 215),
  `tests/test_validation_tools.py` (lines 193, 232),
  `tests/test_validation_tools_multitarget.py` (line 147).

## WHAT

`basic_preflight(sql, params, dialect)` keeps its signature. Only the verdict
string changes:

```python
except ParseError as exc:
    return f"Invalid SQL. ParseError (SQL parsed as {dialect}): {exc}"
```

No docstring change needed (signature and behaviour categories unchanged).

## HOW (integration points)

- No caller changes: `count_tools`, `validation_tools`, and `summarize/sql.py`
  (`validate_where`) all already pass a resolved `dialect` in. The new text
  therefore reaches `count_records`, `validate_sql`, **and** `summarize_columns`
  automatically.
- The dialect goes **before** the sqlglot `{exc}` text (which ends in an
  ANSI-underlined SQL excerpt) — never after.

## ALGORITHM

None beyond the f-string above.

## DATA

Verdict string, e.g. `"Invalid SQL. ParseError (SQL parsed as sqlite): ..."` or
`"... (SQL parsed as tsql): ..."`.

## Test detail

Update the three generic assertions to stop before the dialect name (avoids a
per-test backend-dialect lookup):

```python
assert text.startswith("Invalid SQL. ParseError (SQL parsed as ")
```

applied at `test_count_tools.py:215`, `test_validation_tools.py:193`, and the
direct-preflight test `test_validation_tools.py:232` (which passes `"sqlite"`, so
`... as sqlite): ` is also acceptable if you prefer the tighter pin).

For `test_validation_tools_multitarget.py:147` — where distinguishing sqlite from
tsql is the point — pin the dialect:

```python
assert sqlite_verdict.startswith("Invalid SQL. ParseError (SQL parsed as sqlite): ")
```

No summarize test asserts the prefix, so none needs adding there.

## Gates

`run_pylint_check`, `run_pytest_check` (with the CLAUDE.md exclusion markers),
`run_mypy_check`, `run_ruff_check` — all green.

## LLM prompt

> Implement Step 2 from `pr_info/steps/step_2.md` (context in
> `pr_info/steps/summary.md`). Change `basic_preflight`'s `ParseError` verdict in
> `utils/sql_placeholders.py` to
> `f"Invalid SQL. ParseError (SQL parsed as {dialect}): {exc}"` — dialect
> **before** the sqlglot text. First update the four assertions that pin the old
> prefix (`test_count_tools.py:215`, `test_validation_tools.py:193` and `:232`,
> `test_validation_tools_multitarget.py:147`); use
> `startswith("Invalid SQL. ParseError (SQL parsed as ")` for the generic ones
> and pin `as sqlite)` in the multi-target test. Finish with all quality gates
> green. One commit.
