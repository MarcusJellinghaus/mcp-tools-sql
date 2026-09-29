# review-implementation review log 1

## Round 1 — 2026-09-29
**Findings**:
I'll gather context first.`src/mcp_tools_sql/backends/mssql.py:85` — medium — `_sanitize` redacts only the fully braced escaped form (`{a}}b}`); the unbraced escaped body (`a}}b`) survives unchanged — verified by probe. Replacing `password.replace("}", "}}")` would cover both the braced and the bare doubled-brace form in one pass, matching the issue's "no password-derived form survives".

`tests/backends/conftest.py:49` — medium — `assert_no_leak` hard-codes the same narrow definition of "escaped form" (`_odbc_escape(password)` only), so no test can catch the residual bare-doubled-brace leak above.

`tests/backends/test_mssql.py:272` — medium — `test_password_redacted_in_pyodbc_error` (the only guard on `connect()`'s `exc.args` redaction) still uses the plain `supersecret` and is not parametrized over `LEAKY_PASSWORDS`, while its `get_isolated_connection` twin at `:234` is. The issue's decision was to assert no password-derived form survives *everywhere*.

`tests/backends/test_mssql.py:331` — low — `test_connect_failure_logs_exception_details` asserts only the plain literal is absent from the failure log line; an interior-`}` password is untested on that path.

`tests/backends/conftest.py:44` — low — `_cfg` is underscore-private yet imported by two test modules; drop the underscore or name it `make_config`.
**Decisions**:
Verdict(decision='tasks', tasks=['In src/mcp_tools_sql/backends/mssql.py:85, redact every password-derived form, not just the fully braced escaped one: replace the bare doubled-brace body (password.replace("}", "}}")) as well as the plain and braced forms, so no password-derived string survives sanitization.', 'In tests/backends/conftest.py:49, widen assert_no_leak to also assert the bare doubled-brace form (password.replace("}", "}}")) is absent, alongside the plain password and the full _odbc_escape form.', 'In tests/backends/test_mssql.py:272, parametrize test_password_redacted_in_pyodbc_error over LEAKY_PASSWORDS and assert via assert_no_leak, matching the get_isolated_connection twin at :234.', "In tests/backends/test_mssql.py:331, extend test_connect_failure_logs_exception_details to cover an interior-'}' password and assert no password-derived form appears in the failure log line."], escalate_reason=None)
**Changes**:
applied

## Round 2 — 2026-09-29
**Findings**:
I'll start by gathering context.`tests/backends/conftest.py:33` — low — `_cfg` is underscore-private yet imported by `test_mssql.py` and `test_mssql_connection_string.py`; rename to `make_config` (carried over from round 1, not actioned).
`tests/backends/test_mssql.py:314` — low — `test_connect_failure_logs_exception_details` parametrizes over an ad-hoc `["supersecret", "a}b"]` instead of the shared `LEAKY_PASSWORDS`, so `{x}`, `p;w` and `" sec "` are untested on the failure-log path while every sibling leak test covers them.
**Decisions**:
Verdict(decision='dismiss', tasks=[], escalate_reason=None)
**Changes**:
dismiss
