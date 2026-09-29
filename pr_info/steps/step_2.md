# Step 2 — `build_sanitized_connection_string` builds structurally

See [summary.md](./summary.md) for context. Depends on step 1 (uses
`assert_no_leak`).

Scope: the display/report connection string. The connect-attempt log and the
shared connect helper are step 3.

**This step is a pure structural refactor — no behaviour changes, and no test
is red.** Step 1 already closed the display-string leak:
`build_sanitized_connection_string` is
`_sanitize(_build_connection_string(config), password)`, and after step 1
`_sanitize` strips `_odbc_escape(password)` — exactly the form the built string
contains. The empty-password case also already renders bare `PWD=` today,
because `_sanitize` short-circuits on an empty password.

What this step changes is *how* the guarantee is obtained: the display string
stops depending on the password surviving escaping as a recognisable substring,
which is the fragile assumption that let the bug ship. The tests added here are
therefore characterization tests — written first, green before and after, and
they must stay green across the implementation swap. The empty-password case is
a genuinely new *assertion* (nothing covers it today) but not new behaviour;
without it the refactor could silently start emitting `PWD=***` for an unset
credential.

## WHERE

- `src/mcp_tools_sql/backends/mssql.py` — `build_sanitized_connection_string`
  (currently line 84)
- `tests/backends/test_mssql.py` — `TestSanitizedConnectionString` (line 230)

`_build_connection_string` is **not** modified — signature and body stay as they
are, and its ~14 existing test call sites need no edits.

## WHAT

```python
def build_sanitized_connection_string(config: ConnectionConfig) -> str: ...
```

Signature unchanged, so `src/mcp_tools_sql/verification/connection.py:218` needs
no edit.

## HOW

Replace the `_sanitize(_build_connection_string(config), config.password)` body
with a `model_copy`-based one. `ConnectionConfig` is a plain non-frozen pydantic
`BaseModel`, so `model_copy(update=...)` returns a copy without re-running the
`_normalise_databases` / `_validate_databases` validators. No new imports.

## ALGORITHM

```
build_sanitized_connection_string(config):
    shown = "***" if config.password else ""      # empty password -> bare PWD=
    display = config.model_copy(update={"password": shown})
    return _build_connection_string(display)
```

The real password is never built into the returned string, so nothing has to be
scrubbed out of it. `_odbc_escape("***")` returns `***` unbraced, so the output
stays `PWD=***`.

## DATA

Returns `str` — the full ODBC connection string with `PWD=***` (or bare `PWD=`
when no password is configured). For `trusted_connection` no `PWD=` part is
emitted at all and the result is identical to `_build_connection_string(config)`.

## TDD

Nothing here is red before the implementation change — see the note at the top
of this file. Write the tests first anyway and confirm they are **green against
the step-1 code**; that is what makes them a usable safety net for the swap. The
red-first case for this defect is step 1's `TestSanitize::a}b`.

1. **Rewrite** `test_rest_of_string_matches_raw` (lines 261-276). Its current
   `sanitized == raw.replace("secret", "***")` assertion *is* the substring
   assumption being removed — note it would stay green untouched, because
   `secret` has no special characters, which is exactly why it must go. Replace
   with a split-and-compare:

   ```
   raw_parts = _build_connection_string(c).split(";")
   san_parts = build_sanitized_connection_string(c).split(";")
   assert [p for p in san_parts if not p.startswith("PWD=")] == \
          [p for p in raw_parts if not p.startswith("PWD=")]
   assert "PWD=***" in san_parts
   ```

   (This config has no semicolons inside any value, so splitting is safe.)
2. Add a parametrized test over `LEAKY_PASSWORDS`: build the sanitized string,
   assert `assert_no_leak(s, pw)` and `"PWD=***" in s`. This is green against
   the step-1 code for every case, `a}b` included — it pins the guarantee so the
   swap to structural building cannot weaken it.
3. Add `test_empty_password_renders_bare_pwd`: `_cfg(password="")` with
   `trusted_connection=False` → `"PWD=" in s` and `"PWD=***" not in s`. Also
   green today (`_sanitize` short-circuits on an empty password), but untested
   until now, and the branch the new conditional has to reproduce.
4. Apply the implementation change; update the docstring — it currently describes
   the replace-after-build behaviour, which is what is going away.
5. Re-run; all green. `test_password_replaced_with_stars` and
   `test_trusted_connection_no_redaction_marker` must pass unmodified.

## Checks

`mcp__mcp-tools-py__run_format_code`, then pylint, pytest (`-n auto`), mypy.
Also run `tests/verification/test_connection.py` — it asserts on this string
(`test_verify_connection_mssql_includes_sanitized_conn_string`, line 357).
Commit: tests + implementation together.

## LLM prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_2.md`. Step 1 is
> already committed.
>
> Implement step 2 only: rewrite `build_sanitized_connection_string` in
> `src/mcp_tools_sql/backends/mssql.py` to build the display string structurally
> via `config.model_copy(update={"password": "***" if config.password else ""})`
> instead of building the real string and replacing the password out of it.
>
> In `tests/backends/test_mssql.py`, rewrite `test_rest_of_string_matches_raw` as
> a split-and-compare, add a parametrized leak test over `LEAKY_PASSWORDS` using
> `assert_no_leak`, and add an empty-password test asserting a bare `PWD=`.
>
> This step is a refactor: no test is red beforehand, because step 1 already
> closed the leak by value-based means. Write the tests first and confirm they
> are green against the step-1 code, then swap the implementation and confirm
> they are still green.
>
> Do **not** change `_build_connection_string`'s signature — that would force
> edits to ~14 test call sites for no benefit. Do not touch `connect` or
> `get_isolated_connection` — that is step 3.
>
> Run `run_format_code`, then pylint, pytest with `extra_args: ["-n", "auto"]`,
> and mypy. All must pass. Then make exactly one commit.
