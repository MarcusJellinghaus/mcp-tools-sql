# Step 12 — Isolation contracts, canary, docs

See `pr_info/steps/summary.md` for the overall design.

## Kind
Config + docs. The "test" is `lint-imports` itself, plus a one-off canary.

## WHERE
- `.importlinter`
- `docs/architecture/architecture.md`, `docs/quality-and-security-checks.md`, `docs/cli.md` (check only)

## WHAT
Four forbidden contracts in the shape of `subprocess_isolation` (`source_modules = mcp_tools_sql, tests`).
Put the "why" comment block **above** each section header (as existing contracts do), not inside
the multi-line `ignore_imports` value.

```ini
# Only the SQL layer (mcp_tools_sql.sql_ast) imports sqlglot; callers get strings,
# opaque SourceRef/Predicate and SqlParseError. tests/sql_ast mirrors the owner and may
# assert sqlglot premises (TokenError vs ParseError, expected trees).
[importlinter:contract:sqlglot_isolation]
name = sqlglot Library Isolation
type = forbidden
source_modules =
    mcp_tools_sql
    tests
forbidden_modules =
    sqlglot
ignore_imports =
    mcp_tools_sql.sql_ast.** -> sqlglot
    tests.sql_ast.** -> sqlglot

# Only the backends import DB drivers; callers get DatabaseBackend, BackendError /
# BackendConnectionError and the dependency probes. pyodbc is imported lazily inside
# backends/mssql.py functions (optional extra).
[importlinter:contract:pyodbc_isolation]   ... ignore: mcp_tools_sql.backends.** -> pyodbc
[importlinter:contract:psycopg_isolation]  ... ignore: mcp_tools_sql.backends.** -> psycopg

# sqlite3 additionally allowed in the owner's mirrored tests (tests/backends) and in the
# single shared fixture helper tests/sqlite_fixtures.py (user decision on #93).
[importlinter:contract:sqlite3_isolation]
    ignore: mcp_tools_sql.backends.** -> sqlite3
            tests.backends.** -> sqlite3
            tests.sqlite_fixtures -> sqlite3
```
List only ignore lines that match a real import: import-linter fails on unmatched
`ignore_imports`. If it reports one (e.g. `tests.sql_ast.** -> sqlglot` before any owner test
imports sqlglot), delete that line.

## HOW
1. Add the four contracts after `subprocess_isolation`.
2. `run_lint_imports_check` → PASSED (no indirect-chain failures: every owner edge is ignored).
3. **Canary** (not committed): add `import sqlite3  # canary` to the top of
   `src/mcp_tools_sql/count_tools.py`, run `run_lint_imports_check`, expect `sqlite3_isolation`
   BROKEN; remove the line and re-run → PASSED. If the canary does **not** break the contract,
   write one line to `pr_info/.blocked.txt` and stop.
4. Docs:
   - `architecture.md`: layer diagram gets `sql_ast` beside `config` below `backends`; Key Modules
     table rows for `sql_ast/placeholders.py`, `sql_ast/summarize_queries.py`,
     `sql_ast/source_queries.py`, `backends/postgresql.py`; `backends/base.py` row mentions the
     neutral exceptions and `explain(isolated=...)`; Architecture Enforcement lists the new contracts;
     remove any `utils/sql_placeholders.py` / `summarize/sql.py` / `get_isolated_connection` mention.
   - `quality-and-security-checks.md`: add the four contracts to the isolation-contract list
     (one line each: library → owner).
   - `docs/cli.md`: confirm the pyodbc-missing example (`No module named 'pyodbc'`) is still accurate;
     no edit expected.

## ALGORITHM
None.

## DATA
None.

## Verification
- lint-imports PASSED with all contracts; `run_tach_check` passes.
- pylint, pytest (`-n auto`), mypy, ruff green; `check_file_size` (750) green.
- `search_files`: no `.scratch/` or canary line left.
- Format; one commit.

## Commit
`build(import-linter): isolate sqlglot, pyodbc, psycopg and sqlite3 behind owners`

## LLM prompt
> Read `pr_info/steps/summary.md` and `pr_info/steps/step_12.md`. Add the four isolation
> contracts to `.importlinter` (comments above each section, only ignore lines that match real
> imports), confirm `lint-imports` passes, run the sqlite3 canary exactly as described and revert
> it (if the canary does not break the contract, write one line to `pr_info/.blocked.txt` and
> stop), then update `docs/architecture/architecture.md` and
> `docs/quality-and-security-checks.md`. Use MCP tools only. Run lint-imports, tach, pylint,
> pytest (`-n auto`), mypy and ruff; all must pass. Format, then one commit.
