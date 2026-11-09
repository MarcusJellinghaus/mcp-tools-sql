# Step 11 — `tests/sqlite_fixtures.py`; non-owner tests off `sqlite3` and `sqlglot`

See `pr_info/steps/summary.md` for the overall design.

## Kind
Test-only restructure (no `src` change).

## WHERE
- New `tests/sqlite_fixtures.py` — the single non-owner module allowed to import `sqlite3`.
- Every non-owner test importing `sqlite3` (outside `tests/backends/` and `tests/sql_ast/`):
  `tests/conftest.py`, `test_default_queries.py`, `test_query_limits_tools.py`, `test_query_tools.py`,
  `test_schema_tools.py` (function-local import at ~line 276), `test_server.py`,
  `test_server_verify_tool.py`, `test_toolset.py`, `test_tool_builder.py`,
  `test_update_tools_execution.py`, `cli/test_main_dispatch.py`, `cli/test_tool.py`,
  `cli/test_verify.py`, `summarize/conftest.py`, `summarize/test_source.py`,
  `summarize/test_tools.py`, `summarize/test_tools_query_source.py`.
  Re-check with `search_files` for `^\s*(import sqlite3|from sqlite3)` and for `sqlglot` in `tests/`.
- Not changed: `tests/test_module_imports.py` (its `import sqlite3` is text inside a subprocess
  script, not an import of the test module).

## WHAT
```python
"""SQLite fixture helpers for tests outside tests/backends/.

The only non-owner test module allowed to import sqlite3 (see the
sqlite3_isolation contract in .importlinter). Other tests build and inspect
fixture databases through these helpers, never through sqlite3 directly.
"""

def create_db(path: Path, script: str = "") -> Path:
    """Create (or open) the database file and run *script* via executescript; return *path*."""

def query(path: Path, sql: str, params: Sequence[Any] | Mapping[str, Any] = ()) -> list[tuple[Any, ...]]:
    """Run one statement on a fresh connection; return all rows as tuples (commits writes)."""
```
Add a third helper only if a caller needs something these two cannot express (e.g. dict rows);
keep the module minimal.

## HOW
- Replace `sqlite3.connect(...); conn.executescript(...); conn.commit(); conn.close()` patterns with
  `create_db(path, script)`; replace read-back checks with `query(path, sql, params)`.
- Any `pytest.raises(sqlite3.X)` left in a non-owner test becomes `pytest.raises(BackendError)` /
  `BackendConnectionError` (from `mcp_tools_sql.backends.base`).
- Don't change what tests assert, only how fixtures are built and read.

## ALGORITHM
```
create_db: conn = sqlite3.connect(path); try: conn.executescript(script); conn.commit() finally: conn.close(); return path
query:     conn = sqlite3.connect(path); try: rows = conn.execute(sql, params).fetchall(); conn.commit(); return [tuple(r) for r in rows] finally: conn.close()
```

## DATA
See signatures.

## Tests
The edited tests themselves; add two small tests for the helpers in `tests/test_sqlite_fixtures.py`
(create + query round-trip; query with named params).

## Verification
- `search_files` for `import sqlite3` in `tests/` → only `tests/backends/**`, `tests/sql_ast/**` (none
  expected), `tests/sqlite_fixtures.py`, and the string in `tests/test_module_imports.py`.
- `search_files` for `sqlglot` imports in `tests/` → only `tests/sql_ast/**`.
- pylint, pytest (`-n auto`), mypy, lint-imports, ruff green; format; one commit.

## Commit
`test: route non-owner sqlite fixture setup through tests/sqlite_fixtures.py`

## LLM prompt
> Read `pr_info/steps/summary.md` and `pr_info/steps/step_11.md`. Create
> `tests/sqlite_fixtures.py` with `create_db` and `query` (plus tests), then move every listed
> non-owner test off direct `sqlite3` use onto these helpers, without changing what the tests
> assert. Use MCP tools only. Run pylint, pytest (`-n auto`), mypy, lint-imports and ruff; all
> must pass. Format, then one commit.
