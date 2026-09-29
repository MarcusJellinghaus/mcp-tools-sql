# Step 1 — `_sanitize` redacts the ODBC-escaped password form

See [summary.md](./summary.md) for context.

Scope: `_sanitize` only. The connection-string builder is step 2; the shared
connect helper is step 3. This step also lands the test helper both later steps
use.

## WHERE

- `src/mcp_tools_sql/backends/mssql.py` — `_sanitize` (currently line 73)
- `tests/backends/test_mssql.py` — new module-level helper + new test class

## WHAT

```python
def _sanitize(msg: str, password: str) -> str: ...  # signature unchanged
```

Test module additions (module level, after `_cfg`):

```python
LEAKY_PASSWORDS = ["plain", "a}b", "Sw0rd}", "{x}", "p;w", " sec "]

def assert_no_leak(text: str, password: str) -> None: ...
```

## HOW

`assert_no_leak` asserts that neither the literal password nor
`_odbc_escape(password)` appears in *text*. `_odbc_escape` is already imported in
the test module (line 16). No new imports anywhere.

`LEAKY_PASSWORDS` covers the table from the issue: a plain password, an
interior-`}` password (`a}b` — the case that defeats today's code), a trailing-`}`
password (`Sw0rd}` — passes even unfixed, kept to prove it is not the trigger),
brace-wrapped, semicolon, and surrounding whitespace.

## ALGORITHM

```
_sanitize(msg, password):
    if not password: return msg
    escaped = _odbc_escape(password)
    if escaped != password: msg = msg.replace(escaped, "***")   # longer, more specific first
    return msg.replace(password, "***")
```

The escaped form is replaced first because it is the more specific match; for a
plain password the two forms are identical and the guard skips the redundant pass.

## DATA

Returns `str` — the message with every password-derived form replaced by `***`.
No new data structures.

## TDD

1. New `TestSanitize` class in `tests/backends/test_mssql.py`, parametrized over
   `LEAKY_PASSWORDS`: build `msg = f"Login failed; PWD={_odbc_escape(pw)}"`, call
   `_sanitize(msg, pw)`, assert `assert_no_leak(result, pw)` and `"***" in result`.
   Import `_sanitize` from `mcp_tools_sql.backends.mssql`.
2. Add a case for `password=""` asserting the message is returned unchanged.
3. Run — the `a}b` case fails against the current implementation.
4. Apply the `_sanitize` change; update its docstring to say it redacts driver
   text (`pyodbc.Error.args`) and covers both the literal and the ODBC-escaped
   form.
5. Re-run; all green.

## Checks

`mcp__mcp-tools-py__run_format_code`, then pylint, pytest (`-n auto`), mypy.
Commit: tests + implementation together.

## LLM prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_1.md`.
>
> Implement step 1 only: make `_sanitize` in
> `src/mcp_tools_sql/backends/mssql.py` redact the ODBC-escaped form of the
> password as well as the literal, and add the `LEAKY_PASSWORDS` /
> `assert_no_leak` test helper plus a parametrized `TestSanitize` class to
> `tests/backends/test_mssql.py`.
>
> Write the tests first and confirm the `a}b` case fails before changing
> `_sanitize`. Do not touch `_build_connection_string`,
> `build_sanitized_connection_string`, `connect`, or `get_isolated_connection` —
> those are steps 2 and 3.
>
> Run `run_format_code`, then pylint, pytest with `extra_args: ["-n", "auto"]`,
> and mypy. All must pass. Then make exactly one commit.
