# Step 3 — Implement `format_update_result`

## Goal

Replace the stub `format_update_result(affected_rows, table, key_value)` in
`formatting.py` with a real implementation taking primitives:
`(affected_rows, qualified_table, key_field, key_value) -> str`.

Render text per the affected-row semantics in the issue:
- `0` → plain "no row found" text (used by callers as a normal text result,
  `isError=False`).
- `1` → success confirmation.
- `>1` → result text **begins** with a stable `WARNING:` token on its own
  line so downstream callers can detect the unique-key violation reliably.

## WHERE

- `src/mcp_tools_sql/formatting.py` — replace the stub
- `tests/test_formatting.py` — add a `TestFormatUpdateResult` class

## WHAT

```python
def format_update_result(
    affected_rows: int,
    qualified_table: str,
    key_field: str,
    key_value: Any,
) -> str: ...
```

## HOW

- No new imports — `Any` already imported in `formatting.py`.
- Caller in `update_tools.py` (step 4) joins schema + table to build
  `qualified_table` before calling this function.

## ALGORITHM

```
if affected_rows == 0:
    return f"No row found in {qualified_table} where {key_field}={key_value!r}."
if affected_rows == 1:
    return f"Updated 1 row in {qualified_table} where {key_field}={key_value!r}."
# affected_rows > 1: warning at line start
return (
    f"WARNING: key was supposed to uniquely identify one row\n"
    f"Updated {affected_rows} rows in {qualified_table} "
    f"where {key_field}={key_value!r}."
)
```

## DATA

Returns a `str` in all three branches. The `WARNING:` token always appears
at the start of a line in the >1 branch.

## Tests

TDD: add tests first.

- `tests/test_formatting.py` → new `TestFormatUpdateResult` class:
  - `test_zero_rows_returns_no_row_found_text`: result contains `"No row
    found"`, the qualified table, and the key value; no `WARNING:` token.
  - `test_one_row_success_message`: result mentions `"1 row"`, the
    qualified table, and the key value; no `WARNING:` token.
  - `test_multiple_rows_starts_with_warning_token`:
    `result.splitlines()[0].startswith("WARNING:")` is `True`; result still
    mentions the affected count and the table.
  - `test_qualified_table_with_schema`: passing
    `qualified_table="dbo.customers"` puts that string in the output
    verbatim.
  - `test_qualified_table_without_schema`: passing
    `qualified_table="customers"` (no dot) puts that string in the output
    verbatim.

## LLM Prompt

> Read `pr_info/steps/summary.md` (full file) and `pr_info/steps/step_3.md`.
> Implement Step 3 only: replace the stub `format_update_result` in
> `src/mcp_tools_sql/formatting.py` with the real implementation described
> in this step. Follow TDD: add the five test cases in `TestFormatUpdateResult`
> to `tests/test_formatting.py` before changing the formatter. The
> `WARNING:` token must be at the start of a line in the `>1` branch. Run
> `mcp__tools-py__run_pylint_check`, `mcp__tools-py__run_pytest_check`
> (with the fast unit-test marker exclusion), and
> `mcp__tools-py__run_mypy_check`. Make exactly one commit when green.
