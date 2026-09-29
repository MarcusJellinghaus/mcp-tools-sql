# Summary — Issue #67: MSSQL password redaction defeated by ODBC escaping

## Problem

Two defects in `src/mcp_tools_sql/backends/mssql.py`:

1. **Value-based redaction loses to ODBC escaping.** `_build_connection_string`
   emits `PWD={a}}b}` for the password `a}b` (`_odbc_escape` doubles `}` and
   braces the value). `_sanitize` then searches for the literal `a}b`, which no
   longer exists in that text, and the escaped password survives into the
   verification report (`verification/connection.py:218`) and the connect-attempt
   debug log (`mssql.py:131-134`). A trailing `}` still matches at offset 1, so
   the existing test password `Sw0rd}` passes against the broken code; the
   trigger is a `}` in the **interior** of the password.

2. **Asymmetric connect sites.** `connect()` redacts `exc.args` and re-raises;
   `get_isolated_connection()` calls `pyodbc.connect` bare. `validate_sql` reaches
   it via `_explain` (`validation_tools.py:84`) and returns
   `f"Invalid SQL. {type(exc).__name__}: {exc}"` to the MCP caller, so an
   unredacted driver message reaches the client. Two connect sites on the same
   credential, one protected and one not — that asymmetry is the defect,
   independent of what any given ODBC driver puts in a message.

Classification: security — credential/information disclosure (CWE-532/209).

## Architectural / design changes

**Redaction becomes structural where structure exists.** Today one substring
replace serves three purposes. After this change the two concerns are separated:

| Concern | Before | After |
|---|---|---|
| Display / log connection string | build real string, then `str.replace` the password out | never build the real string — feed the builder a config that already carries the placeholder |
| Driver error text (`pyodbc.Error.args`) | `str.replace` the literal password | `str.replace` the literal **and** `_odbc_escape(password)` |

The display path stops depending on the password surviving escaping as a
recognisable substring. `_sanitize` keeps only its real job — driver text, where
no structure exists and a value-based scrub is the only option available.

**One connect path instead of two.** A private `MSSQLBackend._open_connection()`
owns the attempt log and the args-redacting `try/except`. `connect()` and
`get_isolated_connection()` both call it, so the credential-handling policy lives
in one place rather than being duplicated and kept in sync.

**Deliberate design choices:**

- `_build_connection_string(config)` keeps its single-argument signature and its
  single meaning: "the real connection string". The sanitized variant is produced
  by `config.model_copy(update={"password": ...})`. `ConnectionConfig` is a plain
  non-frozen pydantic model, so `model_copy` works and does not re-run validators.
  (The issue proposed a required `password` parameter instead; the rationale given
  was that a *default* would preserve the bug. `model_copy` carries no such risk —
  there is no second argument to forget — and it avoids editing ~14 builder call
  sites in the test module.)
- Empty password renders bare `PWD=`, not `PWD=***`. This string feeds the
  verification report's `conn_string` row, whose job is exposing misconfiguration;
  masking an unset credential defeats that. `ConnectionConfig.password` defaults
  to `""` with no validator requiring it for non-trusted MSSQL, so this branch is
  genuinely reachable and needs the conditional.
- `_odbc_escape("***")` returns `***` unbraced, so the output stays `PWD=***` and
  existing assertions hold.
- `get_isolated_connection` starts emitting a connect-attempt debug line it does
  not emit today — once per `validate_sql` call on MSSQL. Intended, not a
  regression.
- No compile-time guarantee is bought: someone can still add a third bare
  `pyodbc.connect`. Enforcing that would mean hiding `_build_connection_string`
  behind a wrapper type, which is more machinery than two call sites justify.

**Explicitly out of scope:**

- `validation_tools.py` is untouched, so its four error categories are unaffected.
  The fix lives in the backend because the backend owns the credential, which
  covers every current and future caller.
- No cross-backend abstraction. SQLite has no credentials and no PostgreSQL
  backend exists in the tree. A future PostgreSQL backend will have the same shape
  (password in a DSN, driver errors quoting it); recorded as prior art only, since
  psycopg's error surface differs enough that guessing it now would likely be wrong.
- `mcp-coder-utils` redaction helpers are not adopted. They are key-based (they
  blank dict values by key name) and offer no free-text secret removal, so they do
  not replace `_sanitize`.

## Files created or modified

| Path | Change |
|---|---|
| `src/mcp_tools_sql/backends/mssql.py` | modified — the only source file touched |
| `tests/backends/test_mssql.py` | modified — leak-assertion helper, parametrized leak tests, one rewritten test |
| `pr_info/steps/*` | created — this plan |

No new modules, packages, or folders. No public signature changes:
`build_sanitized_connection_string(config)` keeps its signature, so
`src/mcp_tools_sql/verification/connection.py` needs no edit.

## Steps

Three steps, one commit each, each independently green.

1. **[step_1.md](./step_1.md)** — `_sanitize` also redacts the ODBC-escaped
   password form. Introduces the shared test helper. *Behaviour change; red
   first.*
2. **[step_2.md](./step_2.md)** — `build_sanitized_connection_string` builds
   structurally from a placeholder config. *Refactor; no red test.*
3. **[step_3.md](./step_3.md)** — `_open_connection()` shared by both connect
   sites; routes the attempt log through the structural builder and gives
   `get_isolated_connection` the redacting handler. *Behaviour change; red
   first.*

Order matters, but not for the reason the shape of the plan suggests. Step 1 is
first because it is what actually closes defect 1 everywhere: all three uses of
the substring redaction — the display string, the attempt log, and the driver
error text — go through `_sanitize`, so teaching it the escaped form fixes the
leak at every one of them in a single commit. That is also why it is the only
step with a red test for defect 1.

Steps 2 and 3 then depend on step 1 rather than on each other for correctness:

- Step 2 is a refactor. It replaces a value-based guarantee with a structural
  one so the display string no longer relies on the password surviving escaping
  as a recognisable substring. Nothing is red; its tests are characterization
  tests that must be green before and after.
- Step 3 carries the second defect (`get_isolated_connection` connecting bare),
  which is independent of steps 1 and 2 and is the one red test in that step.
  Its attempt-log assertion is already green after step 1. Step 3 is placed last
  only so that when `_open_connection` routes the attempt log through
  `build_sanitized_connection_string`, that function is already structural —
  otherwise the log's guarantee would silently revert to substring-based.

Both later steps use the `LEAKY_PASSWORDS` / `assert_no_leak` helper added in
step 1, which is the one hard ordering constraint.
