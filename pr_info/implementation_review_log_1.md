# review-implementation review log 1

## Round 1 — 2026-11-09
**Findings**:
Now the source diffs.Source diff reviewed; now checking the contracts and the test changes.src/mcp_tools_sql/sql_ast/summarize_queries.py:204 — low — `validate_where` is a public `sql_ast` function that calls `sqlglot.parse_one` (line 246) but has no `@translate_parse_errors`. That breaks the plan's rule that every public parsing function raises only `SqlParseError`. It is safe today only because `basic_preflight` runs first; add the decorator so a raw `SqlglotError` can never leave `sql_ast`.
src/mcp_tools_sql/backends/mssql.py:227 — low — `conn.timeout = self._config.query_timeout_seconds` runs after the `try/except pyodbc.Error` in `_open_connection`, so a pyodbc error here would escape untranslated. The issue requires translation at every driver call; move the assignment inside the translated block.
**Decisions**:
Verdict(decision='tasks', tasks=['Add `@translate_parse_errors` to `validate_where` in src/mcp_tools_sql/sql_ast/summarize_queries.py:204 so a raw sqlglot exception cannot leave `sql_ast`, even when `basic_preflight` has not run first.', 'In src/mcp_tools_sql/backends/mssql.py `_open_connection`, move `conn.timeout = self._config.query_timeout_seconds` (line 227) inside the `try/except pyodbc.Error` block so a pyodbc error raised there is converted to the neutral backend exception.'], escalate_reason=None)
**Changes**:
applied

## Round 2 — 2026-11-09
**Findings**:
Reviewing the rest of the src diff; next checking other `type(exc).__name__` render sites that the backend translation may have changed.Backends and upper layers look consistent; now checking the `sql_ast` package diff.Code reading done; running the quality checks to confirm the branch is green.NO FINDINGS
**Decisions**:
Verdict(decision='dismiss', tasks=[], escalate_reason=None)
**Changes**:
dismiss
