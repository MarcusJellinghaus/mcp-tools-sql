# review-implementation review log 1

## Round 1 — 2026-09-28
**Findings**:
I'll gather context first.`src/mcp_tools_sql/query_helpers.py:77` — medium — the raw sqlglot `ParseError` text is interpolated verbatim into the rejection message; it contains a newline and ANSI underline escapes, so a `verify` row breaks the one-row-per-line format and emits terminal control codes (baked into `tests/cli/fixtures/verify_snapshot.txt:7-8`). Collapse whitespace and strip escapes, or use only the first line.

`src/mcp_tools_sql/utils/sql_placeholders.py:393` — medium — the gate accepts `SELECT * FROM OPENQUERY(srv, 'DELETE FROM t')` and `OPENROWSET(...)` under both dialects (measured), which execute the embedded statement on a linked server. This is the same "the gate cannot see the body" class that decision 2 rejects `EXEC` for, so the unconditional "proved read-only" claim in `README.md:10` and `docs/architecture/architecture.md:222` overstates what holds on MSSQL.
**Decisions**:
Verdict(decision='tasks', tasks=['In src/mcp_tools_sql/query_helpers.py around line 77, sanitize the sqlglot ParseError text before interpolating it into the rejection message: strip ANSI escape sequences and collapse newlines/whitespace (or use only the first line) so each verify row stays on one line with no terminal control codes. Update tests/cli/fixtures/verify_snapshot.txt accordingly and add a test covering a parse-error message that contains newlines/escapes.', "In src/mcp_tools_sql/utils/sql_placeholders.py around line 393, close the OPENQUERY/OPENROWSET hole: reject statements whose FROM/table sources use OPENQUERY or OPENROWSET, on the same grounds the gate already rejects EXEC (the gate cannot inspect the embedded statement). Add gate tests for SELECT * FROM OPENQUERY(srv, 'DELETE FROM t') and OPENROWSET(...) under both dialects. If the rejection is not implemented, instead soften the unconditional read-only claims in README.md:10 and docs/architecture/architecture.md:222 to state the MSSQL linked-server caveat explicitly — do not leave the claim and the behaviour inconsistent."], escalate_reason=None)
**Changes**:
rebase-needed
**Escalate reason**: rebase
