# Implementation Review (run 2) — branch `verify/first-use-improvements`

This is a second supervisor pass on the same branch. `implementation_review_log_1.md` already triaged the user's four first-use notes — three were
no-ops (already-on-branch) and the fourth shipped as commit `68b6686`
(sanitized MSSQL connection string in `verify` CONNECTION).

Run 2 was launched by the user with the same notes. The goal of this
run is to do a fresh review pass and check whether anything is still
unresolved.

## User's first-use notes (verbatim, same as run 1)

- `examples/prototype_server.py` — do we still need it?
- Replace planning-doc terminology:
  - Financial Data (Bank Fundamentals) → wide data
  - company → customer
  - Provider A → internal system A
  - Bloomberg → system C
  - `bank_fundamentals` / `bank_data` → `wide_data` / `customer_data`
- `verify` prints `[OK] credentials configured` even when no
  credentials are configured.
- `verify` reports `[ERR] select_1 failed` with a raw pyodbc TCP
  timeout when the user wrote `host = "server\name"` (single
  backslash). There is no visible (sanitized) connection string in
  the output.

## Resolution status going into run 2

| # | Note | Status before run 2 |
|---|------|--------------------|
| 1 | prototype_server.py | Deleted in `be37f7d` |
| 2 | Terminology rename | Done in `be37f7d`; fixture names judged out-of-scope in run 1 |
| 3 | credentials [OK] when none configured | Fixed in `70912a3` |
| 4 | Sanitized conn string in verify | Shipped in `68b6686` (this branch) |

The review subagent is therefore asked to confirm closure of items 1–4
*and* surface any other issue that obviously falls within the spirit
of "first-use improvements" (e.g. confusing verify output, missing
sanitization, misleading status labels).

## Round 1 — 2026-05-20

**Findings** (from independent engineer review pass):

1. Note 1 (`prototype_server.py`) — closed; `examples/` directory is
   gone; only stale string matches remain inside `pr_info/` logs.
2. Note 2 (terminology) — closed; zero hits for `Bloomberg`,
   `Provider A`, `bank_fundamentals`, `bank_data`,
   `Bank Fundamentals`, or word-boundary `company` in `src/`,
   `tests/`, `docs/`, `README.md` (only in `pr_info/` logs quoting
   the note). Engineer agreed with run 1: `'Bank A'`/`'Bank B'` are
   placeholder customer-name *data values* in `customers` table
   fixtures, not product terminology.
3. Note 3 (credentials row) — closed at
   `src/mcp_tools_sql/verification/connection.py:144-161`; `[OK]`
   only emitted when `password`, `trusted_connection`, or `sqlite`
   applies. Covered by
   `tests/verification/test_connection.py::test_verify_connection_credentials_missing_for_mssql`.
4. Note 4 (sanitized conn string) — closed;
   `build_sanitized_connection_string` at
   `src/mcp_tools_sql/backends/mssql.py:81-93`, called from
   `verification/connection.py:174-177`. Password masking robust
   (we generate the string, so `PWD=` spelling is fixed). Row shown
   on both success and failure. `server\name` case would have made
   the malformed value obvious at default INFO level.
5. Additional findings — none. Engineer considered three speculative
   items (`_LABEL_WIDTH`, `install_hint` field documentation,
   `--log-level DEBUG` discoverability hint) and rejected all three
   as out of scope / no real friction.

Quality checks (read-only, all green):
ruff, pylint, mypy, pytest (463 passed, 15 skipped — expected real-DB
integration tests).

**Decisions:**

1–4. **Accept closure** — no code change needed.
5. **Skip** the three engineer-considered speculative items; rationale
   matches `software_engineering_principles.md` ("If a change only
   matters when someone makes a future mistake, it's speculative —
   skip it.").

**Changes:** none.
**Status:** zero code changes → loop exits per skill step 7.

### Architectural / unused-code checks (supervisor ran directly)

- `mcp__mcp-tools-py__run_vulture_check` → `vulture produced no
  output.` (clean)
- `mcp__mcp-tools-py__run_lint_imports_check` → `=== PASSED ===
  Contracts: 2 kept, 0 broken` (Layered Architecture KEPT, Forbidden
  external imports KEPT).

## Final Status

Run 2 is a clean no-op. All four user first-use notes were already
fully resolved at the start of this run (run 1 had shipped commit
`68b6686`; the other three notes were closed in earlier branch
commits `be37f7d` and `70912a3`). An independent review pass produced
zero new findings. All quality gates green: ruff, pylint, mypy,
pytest (463 passed / 15 skipped), vulture, lint-imports.

No new commits required from this run except the log itself.
