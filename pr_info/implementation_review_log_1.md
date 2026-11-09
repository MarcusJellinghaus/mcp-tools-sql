# review-implementation review log 1

## Round 1 — 2026-11-09
**Findings**:
Backends, config and tool wiring reviewed. Checking the filter-pattern handling in `execute_and_format` and the timeout tests next.Getting exact line numbers for the findings.`src/mcp_tools_sql/backends/mssql.py:313` — medium — when `iter_readonly_batches` stops early (`max_count_rows`, counting time limit, `gen.close()`), it calls `cursor.close()` with unread rows still pending. With SQL Server default result sets, the ODBC driver may read and discard the rest of the stream before close returns, which would undo the `max_count_rows` bound. Fix: call `cursor.cancel()` before `close()` on early exit, and assert it in `tests/backends/test_mssql_timeout.py`. (Analytical, not run: pyodbc is a C extension, so check against the msodbcsql docs.)
`src/mcp_tools_sql/result_limits.py:195` — low — when a fan-out database fails partway with a non-timeout error, its partly counted `matched` rows stay in `LimitedResult.total` while the footer leaves that database out. The `showing X of Y` total then includes rows from a database reported as errored.
`src/mcp_tools_sql/result_limits.py:189` — low — on SQLite, if the counting deadline interrupts a later fan-out database before it has any matched row, the footer shows `<db> 0+`, not `not queried (limit reached)`.
**Decisions**:
Verdict(decision='tasks', tasks=['In src/mcp_tools_sql/backends/mssql.py around line 313 (iter_readonly_batches): on early exit (max_count_rows reached, counting time limit hit, or generator closed), call cursor.cancel() before cursor.close() so the ODBC driver does not drain the remaining result stream. Add a test in tests/backends/test_mssql_timeout.py asserting cancel() is called before close() on each early-exit path, and that it is not called on normal exhaustion.', "In src/mcp_tools_sql/result_limits.py around line 195: when a fan-out database fails with a non-timeout error partway through counting, roll back its partially counted matched rows from LimitedResult.total so the 'showing X of Y' total only includes databases the footer reports as counted. Add a test covering a mid-count non-timeout failure in a fan-out run.", "In src/mcp_tools_sql/result_limits.py around line 189: when the counting deadline interrupts a later fan-out database before it has produced any matched row (e.g. SQLite progress-handler interrupt), report it in the footer as 'not queried (limit reached)' rather than '<db> 0+'. Add a test for this case."], escalate_reason=None)
**Changes**:
applied

## Round 2 — 2026-11-09
**Findings**:
Backends and result_limits look sound so far; checking the tool wiring, config and validation changes next.Reviewing remaining tool paths (summarize, verify) for timeout handling gaps.`src/mcp_tools_sql/result_limits.py:200` — medium — The round-1 fix takes an errored fan-out database's matched rows out of `counted`/`total`, but its display rows stay in `rows`. That makes `showing X of Y` wrong, and it can show more rows than the total. Example: db1 shows 80 rows then fails with a non-timeout error; db2 matches 30; max_rows is 100. The output says `showing 100 of 30 rows (max_rows=100 reached)`, and 80 of those 100 rows come from a database the footer reports as errored. Fix: drop that database's rows from `rows` too (record `len(rows)` before the loop and truncate back to it), or keep its count. No test covers this mismatch. (Worked out from the code, not run.)

`src/mcp_tools_sql/result_limits.py:151` — low — If db1 ends exactly at `max_count_rows`, the first matched row of db2 sets `stop="max_count"` before `count.matched` goes up. db2 is then rendered as `<db> 0+` in the `Matched:` footer, which is the same `0+` defect round 1 fixed for the counting-deadline case. It should read `not queried (limit reached)` (set `count.queried = False` when `count.matched == 0`). (Worked out from the code, not run.)
**Decisions**:
Verdict(decision='tasks', tasks=["In src/mcp_tools_sql/result_limits.py around line 200: when a fan-out database fails with a non-timeout error, also drop the display rows it already contributed. Record len(rows) before that database's loop and truncate rows back to that length on error, so the rows shown match the counted total and 'showing X of Y' can never have X > Y. Add a test where db1 adds display rows and then raises a non-timeout error while db2 succeeds, and assert the shown rows and total only reflect db2.", "In src/mcp_tools_sql/result_limits.py around line 151: when stop='max_count' fires on a database's first matched row (so count.matched == 0), set count.queried = False so the footer reads 'not queried (limit reached)' instead of '<db> 0+'. Add a test where db1 ends exactly at max_count_rows and check db2's footer text."], escalate_reason=None)
**Changes**:
applied

## Round 3 — 2026-11-09
**Findings**:
Tests and mypy pass. Last check: confirming summarize's metadata/probe calls sit inside the new timeout branch.NO FINDINGS
**Decisions**:
Verdict(decision='dismiss', tasks=[], escalate_reason=None)
**Changes**:
dismiss
