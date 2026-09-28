# Step 4 — Stop truncating verify row labels

Read [summary.md](./summary.md) first. This is decision 13, and it comes before
step 5 so the snapshot fixture settles at the new padding before new rows land.

## WHERE

- `src/mcp_tools_sql/cli/commands/verify.py`
- `tests/cli/test_verify.py`
- `tests/cli/fixtures/verify_snapshot.txt` (regenerated)

## WHAT

Delete `_pad` (`verify.py:15-23`) and inline the padding in `_format_row`:

```python
parts = [symbol, label.ljust(_LABEL_WIDTH)]
```

`str.ljust` returns the string unchanged when it is already at least `width`
long, so this *is* the no-truncation behaviour — no conditional needed. Keep
`_LABEL_WIDTH = 28` as a minimum pad so ordinary rows stay aligned; a longer
label pushes its own value column right.

`_format_row` was `_pad`'s only caller and no test references either name, so the
function goes rather than getting edited.

## HOW

Update `_LABEL_WIDTH`'s comment/name context if it reads as a maximum anywhere —
it is now a minimum.

Why not simply raise the width: two labels collide whenever
`width <= len(name) + 11`, so 40 would just move the collision from 17-character
query names to 29-character ones. Dropping truncation removes the class.

## ALGORITHM

None.

## DATA

Row strings grow for labels of 28+ characters. Today's fixture already carries
one truncated label (`mismatched_params.max_rows_d`), which becomes
`mismatched_params.max_rows_default`.

## TESTS (write first)

- A unit test on `_format_row`: a label longer than `_LABEL_WIDTH` appears in
  full, and its value is still present and separated. This is the regression that
  pins decision 13.
- A short label is still padded to the same column as today.
- Then regenerate `tests/cli/fixtures/verify_snapshot.txt`.
  `test_verify_cli_queries_updates_snapshot` will fail on the padding change.
  **Regenerate from actual captured output — do not hand-pad.** Print or dump the
  `actual` string the test builds and write exactly that. Review the diff: the
  only expected change is the `mismatched_params.max_rows_d` line becoming
  untruncated and its value column shifting right. Any other change means
  something unintended moved.

## LLM PROMPT

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_4.md`.
>
> Implement step 4 test-first: add the `_format_row` long-label test to
> `tests/cli/test_verify.py`, watch it fail, then delete `_pad` from
> `src/mcp_tools_sql/cli/commands/verify.py` and inline `label.ljust(_LABEL_WIDTH)`
> in `_format_row`.
>
> Then regenerate `tests/cli/fixtures/verify_snapshot.txt` from the actual output
> of `test_verify_cli_queries_updates_snapshot` — never hand-pad it — and check
> the diff shows only the un-truncated `mismatched_params.max_rows_default` label
> and its shifted value.
>
> Then run `run_format_code`, `run_pylint_check`, `run_pytest_check` with
> `extra_args: ["-n", "auto"]` and `run_mypy_check`. All must pass. Commit as one
> commit.
