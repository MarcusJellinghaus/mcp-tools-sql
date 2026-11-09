# Step 9 — Upper layers drop raw driver exception types

See `pr_info/steps/summary.md` for the overall design.

## Kind
Restructure. Tests adjusted first (stand-in exceptions → neutral ones).

## Precondition
Steps 6–8 are done: `search_files` for `get_isolated_connection` in `src/` returns nothing and
`src/mcp_tools_sql/backends/sqlite.py` / `mssql.py` both call `wrap_driver_error` (directly or via
`_translate_pyodbc`). If not, write one line to `pr_info/.blocked.txt` and stop.

## WHERE
- `src/mcp_tools_sql/count_tools.py`, `validation_tools.py`, `summarize/source.py`,
  `summarize/tools.py`, `cli/commands/tool_dispatch.py`
- Tests: `tests/summarize/test_source.py`, `tests/summarize/test_tools.py`,
  `tests/summarize/test_tools_query_source.py`, `tests/cli/test_tool_dispatch.py`,
  `tests/test_tool_timeouts.py` (if it still uses a raw stand-in), and any other test using
  `sqlite3.*Error(...)` / `pyodbc.*` as a mock side effect (`search_files` for `sqlite3\.\w*Error\(`).

## WHAT
No new functions. Remove:
- `import sqlite3`, the `try: import pyodbc ... except ImportError` blocks, `_PYODBC_ERROR`,
  `_INVALID_SQL_EXC` (`count_tools`, `validation_tools`), `INVALID_SQL_EXC` (`summarize/source.py`
  and its import in `summarize/tools.py`, plus the comment block explaining its location).
Replace with:
- `except BackendError as exc:` in the three "Invalid SQL." branches and in
  `summarize/source.py::_describe_or_none`.
- `tool_dispatch._CONNECTION_EXC = (RuntimeError, BackendConnectionError)` (single definition).

## HOW
- Import `BackendError` / `BackendConnectionError` from `mcp_tools_sql.backends.base`.
- Keep branch order: `QueryTimeoutError` → `BackendError` ("Invalid SQL.") →
  `(KeyError, TypeError, ValueError)` → `RuntimeError` → `Exception`.
- Tests: replace stand-ins, keeping the class name the message pins, e.g.
  `sqlite3.OperationalError("denied")` → `BackendConnectionError("denied", original_class="OperationalError")`,
  `sqlite3.ProgrammingError("bad SQL")` → `BackendError("bad SQL", original_class="ProgrammingError")`.
- `tests/cli/test_tool_dispatch.py`: drop `import sqlite3` and the `pyodbc` try-import/skipif test;
  classification tests use `BackendConnectionError` (→ `EXIT_CONFIG`) and `BackendError`
  (→ `EXIT_BACKEND`); message test asserts `"OperationalError: unable to open database file"`.

## ALGORITHM
None (deletions and type swaps).

## DATA
Messages and exit codes unchanged.

## Verification
- `search_files` for `sqlite3|pyodbc` in `src/mcp_tools_sql/` outside `backends/` → only
  `verification/dependencies.py` (step 10) and comments/docstrings.
- pylint, pytest (`-n auto`), mypy, lint-imports, ruff green; format; one commit.

## Commit
`refactor: upper layers catch only neutral backend exceptions`

## LLM prompt
> Read `pr_info/steps/summary.md` and `pr_info/steps/step_9.md`. Check the precondition first.
> Replace the raw sqlite3/pyodbc stand-in exceptions in the listed tests with
> `BackendError`/`BackendConnectionError` (same `original_class`), then delete the raw driver
> exception tuples and `try: import pyodbc` blocks from `count_tools`, `validation_tools`,
> `summarize/source.py`, `summarize/tools.py` and `cli/commands/tool_dispatch.py`, catching only
> the neutral exceptions. Messages and exit codes must stay identical. Use MCP tools only. Run
> pylint, pytest (`-n auto`), mypy, lint-imports and ruff; all must pass. Format, then one commit.
