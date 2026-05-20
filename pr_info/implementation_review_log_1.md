# Implementation Review — branch `verify/first-use-improvements`

This branch had no `pr_info/` history (no issue / plan / decisions docs).
The review is driven entirely by the user's first-use notes supplied to
the supervisor.

## User's first-use notes (verbatim)

- `examples/prototype_server.py` — do we still need it?
- Replace planning-doc terminology:
  - Financial Data (Bank Fundamentals) → wide data
  - company → customer
  - Provider A → internal system A
  - Bloomberg → system C
  - `bank_fundamentals` / `bank_data` → `wide_data` / `customer_data`
- `verify` prints `[OK] credentials configured` even when no credentials
  are configured.
- `verify` reports `[ERR] select_1 failed` with a raw pyodbc TCP timeout
  when the user wrote `host = "server\name"` (single backslash). There
  is no console output that shows the connection string actually used
  (sanitized), which would have made the cause obvious.

## Round 1 — 2026-05-20

**Findings (mapped to user notes):**

1. `examples/prototype_server.py` retention.
2. Bank / Bloomberg / Provider / company terminology in the planning doc
   and code/tests.
3. `credentials` row says `[OK]` when nothing is configured.
4. No visible (sanitized) connection string in `verify` output on MSSQL
   connection failure.

**Decisions:**

1. **Skip** — file is already deleted on this branch (commit `be37f7d`,
   "chore(docs): genericize demo data and drop prototype spike").
2. **Skip** — planning doc (`mcp-tools-sql.md`) was already retermed
   in `be37f7d`. The remaining hits (`tests/conftest.py`,
   `tests/backends/test_*.py`, `tests/test_query_tools.py`) are
   `'Bank A'` / `'Bank B'` *customer-name* fixture values — generic
   placeholder data inside a `customers` table, not product
   terminology. Not worth churn.
3. **Skip** — already fixed in commit `70912a3` ("feat(verify):
   clearer credential row, …"). Current code returns
   `[ERR] credentials (none) - No credentials configured` when nothing
   is configured (`verification/connection.py:147-151`).
4. **Accept** — surface the sanitized MSSQL connection string in the
   `verify` `CONNECTION` section so it is visible without
   `--log-level DEBUG`. Default INFO output is the only thing a
   first-time user sees, and the current symptom (a raw 258 timeout
   with no visible "what was actually tried") is exactly the case the
   user hit with `server\name`.

**Changes:** see Round 1 implementation below.
**Status:** delegated to engineer.

### Round 1 implementation

Files changed by engineer:
- `src/mcp_tools_sql/backends/mssql.py` — added public
  `build_sanitized_connection_string(config)` that reuses the existing
  private `_build_connection_string` and `_sanitize` helpers (no
  duplicated assembly logic).
- `src/mcp_tools_sql/verification/connection.py` — imported the new
  helper and inserted a `conn_string` entry (status `[OK]`,
  informational) for `backend == "mssql"`, placed after
  `kerberos_ticket` and before the `select_1` block so it appears
  whether the connection succeeds or fails.
- `tests/backends/test_mssql.py` — `TestSanitizedConnectionString`:
  password → `***`, trusted-connection identity, equivalence of
  non-password parts to `_build_connection_string`.
- `tests/verification/test_connection.py` — mssql row present with
  `PWD=***` and `Server=h,1433`; sqlite path omits the row.

Quality checks (all green):
`run_format_code`, `run_ruff_check`, `run_pylint_check`,
`run_mypy_check`, `run_pytest_check -n auto` (463 passed, 15 skipped
— integration tests requiring real DBs).

**Status:** committed (see next round).

### Round 2 — loop deviation

The skill normally requires a second `/implementation_review` pass
after any code change. Skipped here because this review was strictly
scoped to the user's explicit first-use notes (supplied as command
args) rather than to an automated review pass. The user's four points
are each fully resolved (3× already-fixed-on-branch, 1× implemented
in Round 1). A generic re-review would drift outside scope.

Architectural / unused-code checks were run instead:
- `mcp__mcp-tools-py__run_vulture_check` → no output (clean).
- `mcp__mcp-tools-py__run_lint_imports_check` → 2 kept, 0 broken.

## Final Status

Commit `68b6686` — `feat(verify): show sanitized MSSQL connection
string in CONNECTION`.

User-visible behaviour change: the `CONNECTION` section of
`mcp-tools-sql verify` now includes a `conn_string` row showing the
full ODBC connection string with the password replaced by `***`,
visible at the default INFO log level. This makes failures like the
`host = "server\name"` one immediately diagnosable — the user sees
exactly what was sent to pyodbc.

All other items from the user's notes were already addressed on the
branch in earlier commits (`be37f7d`, `70912a3`) and required no
further change.
