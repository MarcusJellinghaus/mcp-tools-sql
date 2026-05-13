# Implementation Review Log — Issue #7 (MS SQL Server backend, pyodbc)

Branch: `7-ms-sql-server-backend-pyodbc`
Base: `main`
Started: 2026-05-13

This log captures each review round: findings reported by the review subagent,
triage decisions (accept / skip with reason), and the changes implemented.

## Round 1 — 2026-05-13

**Findings** (from `/implementation_review` subagent):

1. `MSSQLBackend.connect()` rebuilds the pyodbc exception with `raise type(exc)(sanitized) from exc` — passes a single string to constructors that may expect a `(sqlstate, message)` tuple. Test fake is a single-arg `Error(Exception)` so this never surfaces.
2. `verify.py:_check_sql_explain` docstring says MSSQL `backend.explain` "currently raises `NotImplementedError`... until the MSSQL backend lands (issues #5/#6)" — stale, since the MSSQL backend lands in this PR.
3. Integration fixture `mssql_db` teardown wraps every drop in `with suppress(Exception)` — partial setup failures aren't caught outside that block. Low risk.
4. `_sanitize` only redacts the literal password value via `.replace`. If pyodbc URL-encoded or otherwise transformed the password in the error message, the literal replace would miss it. In practice pyodbc echoes verbatim.
5. `_iter_placeholders` in `utils/sql_placeholders.py` only used internally by `extract_param_names`. Could be inlined.

No critical issues; CI passing; branch up to date with `origin/main`.

**Decisions**:

- **Accept #1** — exception shape is part of the public surface; preserving sqlstate matters for callers. Fix by sanitizing `exc.args` in place and bare-`raise`.
- **Accept #2** — Boy Scout fix in a file already modified by this PR; keeps documentation accurate.
- **Skip #3** — speculative; reviewer admits low risk; existing pattern fine.
- **Skip #4** — speculative defensive coding for hypothetical pyodbc behavior; not warranted (YAGNI).
- **Skip #5** — cosmetic; do not change working code for style preference.

**Changes**:

- `src/mcp_tools_sql/backends/mssql.py` — `connect()` now sanitizes string elements of `exc.args` in place and bare-re-raises, preserving the original `pyodbc.Error` instance (type, sqlstate, traceback). Docstring updated.
- `tests/backends/test_mssql.py` — `fake_pyodbc` exposes an `OperationalError` subclass; redaction test uses a 2-arg `OperationalError("08001", "Login failed; PWD=supersecret")` and asserts identity / isinstance / sqlstate preservation in addition to redaction.
- `src/mcp_tools_sql/cli/commands/verify.py` — `_check_sql_explain` docstring refreshed to describe the live MSSQL `SET SHOWPLAN_TEXT ON/OFF` explain path.

**Test results**: 345 passed, 2 skipped; pylint / mypy / ruff clean.

**Status**: committed as `5b3ee66` ("fix(mssql): preserve pyodbc.Error shape on redact; refresh verify docstring"), pushed.

## Round 2 — 2026-05-13

**Findings** (from `/implementation_review` subagent):

1. `MSSQLBackend.explain()` runs `SET SHOWPLAN_TEXT ON/OFF` on a fresh cursor, but `SET` is connection-scoped in MSSQL. The inner `try/finally` handles synchronous failure (the realistic case); a hypothetical thread sharing the connection that hits `cursor.close()` between the two `execute` calls would observe leaked SHOWPLAN state.
2. `_sanitize` only does a literal `.replace` of the password. If pyodbc ever emits the password URL-encoded or case-folded, redaction would silently miss. Pre-existing — flagged for future hardening only.

Round 1 fixes verified correctly applied: exception preserves type/sqlstate/traceback via in-place `exc.args` mutation, redaction test covers identity/isinstance/sqlstate, `_check_sql_explain` docstring matches the live MSSQL path.

**Decisions**:

- **Skip #1** — speculative; the realistic synchronous failure path is already covered. No threading is in scope; not worth defensive code for a hypothetical future use case (YAGNI).
- **Skip #2** — reviewer explicitly notes "pre-existing through Round 1, not new — flagging for future hardening only". Already triaged as Skip in Round 1 (#4). Pre-existing pattern.

**Changes**: none.

**Status**: no code changes — review loop terminates.

## Final Status

- **Rounds run**: 2 (Round 1 produced 2 accepted fixes; Round 2 produced 0 changes).
- **Commits this review**:
  - `5b3ee66` — fix(mssql): preserve pyodbc.Error shape on redact; refresh verify docstring
  - `50af60e` — chore: whitelist pytest fixtures for vulture (issue #7)
- **Vulture**: clean.
- **Lint-imports**: PASSED (2 contracts kept, 0 broken).
- **CI**: PASSED at HEAD.
- **Branch**: up to date with `origin/main`; ready for PR / merge.


