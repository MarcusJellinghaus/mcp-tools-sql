# Step 2 — `validate_sql` tool + `ValidationTools` (not yet wired)

Replace the `validation_tools.py` stub with the full `validate_sql` implementation: pre-flight checks, exception ladder, SHOWPLAN dance using the Step 1 isolation primitive. Includes unit tests against a mocked backend plus SQLite integration tests. The tool is **not** yet registered with the server — that lands in Step 3.

## WHERE

- `src/mcp_tools_sql/validation_tools.py` — replace stub.
- `tests/test_validation_tools.py` — new file (mirrors src path).

## WHAT

### Module-level (`validation_tools.py`)
```python
"""MCP tools for SQL validation via the database's EXPLAIN mechanism."""

from __future__ import annotations
import sqlite3
from typing import TYPE_CHECKING, Annotated, Any

import sqlparse
from pydantic import Field

from mcp_tools_sql.tool_logging import log_tool_call
from mcp_tools_sql.utils.sql_placeholders import (
    extract_param_names,
    substitute_named_with_literals,
)

try:
    import pyodbc  # pylint: disable=import-error
    _PYODBC_ERROR: tuple[type[Exception], ...] = (pyodbc.Error,)
except ImportError:
    _PYODBC_ERROR = ()

_SESSION_KEYWORDS = frozenset({"USE", "SET", "DECLARE"})

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP
    from mcp_tools_sql.backends.base import DatabaseBackend
```

### Private helpers
- `def _count_statements(sql: str) -> int` — `len([s for s in sqlparse.parse(sql) if any(not (t.is_whitespace or t.ttype in sqlparse.tokens.Comment) for t in s.flatten())])`.
- `def _first_keyword(sql: str) -> str | None` — flatten tokens of the first parsed statement; return uppercased value of the first non-whitespace, non-comment, non-punctuation token, or `None` if none found.
- `def _preflight(sql: str, params: dict[str, Any] | None) -> str | None` — returns an error verdict string if any pre-flight check fails, else `None`.

### Tool description constant
```python
_DESCRIPTION = (
    "Validate a SQL string via the database's EXPLAIN mechanism. "
    "Returns 'Valid.' or a labelled error verdict. "
    "Setting return_plan=True appends the execution plan on success. "
    "validate_sql does NOT execute the statement — safe for SELECT, "
    "UPDATE, INSERT, DELETE, and DDL (CREATE/DROP/ALTER)."
)
```

### `ValidationTools`
```python
class ValidationTools:
    def __init__(self, backend: DatabaseBackend, backend_name: str) -> None:
        self._backend = backend
        self._backend_name = backend_name

    def register(self, mcp: FastMCP) -> None:
        backend = self._backend
        backend_name = self._backend_name

        async def validate_sql(
            sql: Annotated[str, Field(description="The SQL to validate.")],
            params: Annotated[
                dict[str, Any] | None,
                Field(description="Bound values for :name placeholders."),
            ] = None,
            return_plan: Annotated[
                bool,
                Field(description="Append the execution plan on success."),
            ] = False,
        ) -> str:
            async with log_tool_call(
                "validate_sql", params or {}, sql=sql
            ) as rec:
                rec.record(rows=0, cols=0)
                verdict = _preflight(sql, params)
                if verdict is not None:
                    return verdict
                try:
                    plan = _explain(backend, backend_name, sql, params)
                except (sqlite3.Error, *_PYODBC_ERROR) as exc:
                    return f"Invalid SQL. {type(exc).__name__}: {exc}"
                except (KeyError, TypeError, ValueError) as exc:
                    return f"Invalid parameters. {type(exc).__name__}: {exc}"
                except RuntimeError as exc:
                    return (
                        f"Database connection error. "
                        f"{type(exc).__name__}: {exc}"
                    )
                except Exception as exc:  # noqa: BLE001
                    return f"Unexpected error. {type(exc).__name__}: {exc}"
                if return_plan:
                    return f"Valid.\nExecution plan:\n{plan}"
                return "Valid."

        mcp.add_tool(
            validate_sql, name="validate_sql", description=_DESCRIPTION
        )
```

### Backend-dispatch helper
```python
def _explain(
    backend: DatabaseBackend,
    backend_name: str,
    sql: str,
    params: dict[str, Any] | None,
) -> str:
    if backend_name == "sqlite":
        return backend.explain(sql, params)
    # mssql / pyodbc — run SHOWPLAN dance on an isolated connection.
    explain_sql = substitute_named_with_literals(sql, params or {})
    with backend.get_isolated_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("SET SHOWPLAN_TEXT ON")
            try:
                cursor.execute(explain_sql)
                rows = cursor.fetchall()
            finally:
                cursor.execute("SET SHOWPLAN_TEXT OFF")
            return "\n".join(r[0] for r in rows if r and r[0])
        finally:
            cursor.close()
```

## HOW

- `_preflight` runs in order: empty → multi-statement → session-control first keyword → missing param names.
- Empty rule applies to whitespace-only as well (`sql.strip() == ""`).
- Missing-name verdict uses the deterministic min of missing names so the message is stable: `f"Invalid parameters. KeyError: '{min(missing)}'"`.
- `_count_statements` filters out whitespace-only statements so trailing newlines / `";"` do not falsely trigger multi-statement.
- The exception ladder ordering is **specific → general**: `sqlite3.Error` + `pyodbc.Error` first, then `KeyError`/`TypeError`/`ValueError`, then `RuntimeError`, then `Exception`. Note: `sqlite3.Error` and `pyodbc.Error` both extend `Exception` only via `Warning`/`Exception` — they do NOT subclass `KeyError`/`TypeError`/`ValueError`, so ordering is safe.
- `BLE001` (`blind-except`) is suppressed on the catch-all by design — Decision #8 (never re-raise to the LLM).
- `rec.record(rows=0, cols=0)` is set once at the top of the body so the success INFO log line always carries zeros (validate_sql returns a string verdict, not tabular data).

## ALGORITHM

```
verdict = _preflight(sql, params)        # 4 checks, no DB call
if verdict: return verdict
try:
    plan = _explain(backend, backend_name, sql, params)
except <5-bucket ladder>: return "<Label>. <Type>: <msg>"
return "Valid." + (f"\nExecution plan:\n{plan}" if return_plan else "")
```

## DATA

- Returns `str` (one of: `"Valid."`, `"Valid.\nExecution plan:\n..."`, `"Invalid SQL. ..."`, `"Invalid parameters. ..."`, `"Database connection error. ..."`, `"Unexpected error. ..."`).

## Tests — `tests/test_validation_tools.py`

Use a `FastMCP` + `create_connected_server_and_client_session` pattern matching `tests/test_query_tools.py`. Call the tool through the MCP client so registration is exercised end-to-end. (Even though server wiring lands in Step 3, the `ValidationTools(backend, "sqlite").register(mcp)` path is callable directly here.)

### Pre-flight (no DB round-trip — spy on `backend.explain` via `MagicMock` and assert `explain.call_count == 0`)
- [ ] Empty SQL → `Invalid SQL. Error: empty SQL`
- [ ] Whitespace-only SQL → `Invalid SQL. Error: empty SQL`
- [ ] Missing param name → `Invalid parameters. KeyError: '<name>'`
- [ ] Multi-statement (`SELECT 1; SELECT 2`) → `Invalid SQL. Error: multiple statements not supported`
- [ ] `USE other_db` → `Invalid SQL. Error: USE statements not supported`
- [ ] `SET QUOTED_IDENTIFIER ON` → `Invalid SQL. Error: SET statements not supported`
- [ ] `DECLARE @x INT` → `Invalid SQL. Error: DECLARE statements not supported`

### Param handling
- [ ] `params=None` + non-parameterised SQL → `Valid.`
- [ ] `params={}` + non-parameterised SQL → `Valid.` (symmetric)
- [ ] Extra param names in `params` (not in SQL) are silently ignored — `Valid.`

### Success (via `sqlite_db` fixture)
- [ ] Valid SELECT → `Valid.` (default)
- [ ] Valid SELECT with `return_plan=True` → starts with `Valid.\nExecution plan:\n` and the plan text is non-empty
- [ ] Valid UPDATE (`UPDATE customers SET name = 'X' WHERE id = 999`) → `Valid.` and customer 999 still does not exist afterwards (confirms EXPLAIN never executes)
- [ ] Valid DDL (`DROP TABLE customers`) → `Valid.` and `customers` table still exists afterwards (confirms DDL is not executed either)

### Failure
- [ ] Syntax error (`SELEKT * FROM customers`) → starts with `Invalid SQL. ` and includes the sqlite3 error type name
- [ ] Unknown table (`SELECT * FROM no_such_table`) → starts with `Invalid SQL. `
- [ ] `return_plan=True` on invalid SQL → error verdict only, no `Execution plan:` substring
- [ ] `RuntimeError` (backend closed via `backend.close()`) → starts with `Database connection error. RuntimeError: `

### Mark MSSQL-specific failure tests as Step 3 work
Unsupported-param-type and non-finite-float tests need the MSSQL path (`_sql_literal`); they live in Step 3.

## Commit & checks

Commit message: `feat(validation): implement validate_sql tool`.

Run before commit:
- `mcp__mcp-tools-py__run_format_code`
- `mcp__mcp-tools-py__run_pytest_check` with `extra_args=["-n", "auto"]`
- `mcp__mcp-tools-py__run_pylint_check`
- `mcp__mcp-tools-py__run_mypy_check`

All must pass.

## LLM prompt for this step

> Implement Step 2 of issue #8 per `pr_info/steps/summary.md` and `pr_info/steps/step_2.md`. Replace the `validation_tools.py` stub with the full implementation: defensive `pyodbc` import, `_preflight` helper (4 checks), `_explain` helper that dispatches on `backend_name`, `ValidationTools` class with `validate_sql` async tool registered via `mcp.add_tool`. Use `log_tool_call` and `rec.record(rows=0, cols=0)`. Add `tests/test_validation_tools.py` with all pre-flight, param-handling, success and failure cases (SQLite path). Do NOT wire into `server.py` — that is Step 3. Run format / pytest / pylint / mypy and commit as one commit.
