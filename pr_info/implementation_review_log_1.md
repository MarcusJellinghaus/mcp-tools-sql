# review-implementation review log 1

## Round 1 — 2026-08-26
**Findings**:
I'll gather context systematically, starting with the knowledge base and issue details.`src/mcp_tools_sql/summarize/source.py:347` — medium — `_describe_or_none` discards `describe_columns`' name rejection, collapsing "DMF says the projection is unaddressable" into "DMF failed, fall back". On T-SQL the designed duplicate/unnamed-column message (`_NAME_REJECTION`, naming the aliasing recovery) therefore never reaches the caller: the fallback probe runs `SELECT TOP 5 * FROM (<source>) AS src`, which SQL Server rejects with raw error 8156/8155, and that raw driver text is what is returned. The guard is unit-tested at `describe_columns` level (`tests/summarize/test_source.py:576`) but unreachable end-to-end; the only end-to-end duplicate-column test (`tests/summarize/test_tools_query_source.py:195`) is SQLite-only. This is the issue's motivating example (`SELECT * FROM a JOIN b` with two `id`s) on the primary backend — the "Remaining edge cases" bullet requires the aliasing error on both backends.

`src/mcp_tools_sql/summarize/source.py:122` — medium — `ROW_LIMITED_NOTE` states the wrong fact. Decision 10's note exists because the deep view executes the source 3+N times (4+N on SQLite), so a row-limited source can profile a *different population* per pass and the count, statistics and value lists can quietly disagree. The shipped wording ("the statistics describe only the rows it returns, not the full result set") is trivially true of any limited query and omits the separate-executions hazard entirely. The "document" half of decision 10 is also absent — neither `_DESCRIPTION` in `src/mcp_tools_sql/summarize/tools.py:73` nor the doc updates mention non-determinism across passes.
**Decisions**:
Verdict(decision='dismiss', tasks=[], escalate_reason=None)
**Changes**:
dismiss
