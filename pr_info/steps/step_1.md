# Step 1 — Move `utils/sql_placeholders.py` → `sql_ast/placeholders.py` (move step)

See `pr_info/steps/summary.md` for the overall design.

## Kind
Pure move (refactoring principles: move as-is, only import edits). No logic changes,
no new tests (existing tests move with the module).

## WHERE
- New package: `src/mcp_tools_sql/sql_ast/__init__.py` (docstring only:
  `"""SQL layer: the only package that imports sqlglot."""`).
- `src/mcp_tools_sql/utils/sql_placeholders.py` → `src/mcp_tools_sql/sql_ast/placeholders.py`
- `tests/test_sql_placeholders.py` → `tests/sql_ast/test_placeholders.py`
- `tests/test_basic_preflight.py` → `tests/sql_ast/test_basic_preflight.py`
- New `tests/sql_ast/__init__.py` (empty).
- Config: `tach.toml`, `.importlinter`.

## WHAT
No new functions. Every import `mcp_tools_sql.utils.sql_placeholders` becomes
`mcp_tools_sql.sql_ast.placeholders`. Callers today:
`count_tools.py`, `query_helpers.py`, `validation_tools.py`, `backends/mssql.py`,
`summarize/source.py`, `summarize/sql.py`, and tests
`test_basic_preflight.py`, `test_query_tools_readonly.py`, `test_sql_placeholders.py`,
`summarize/test_source.py`.

## HOW
1. Create `src/mcp_tools_sql/sql_ast/__init__.py` and `tests/sql_ast/__init__.py`.
2. `mcp__mcp-workspace__move_file` the source and the two test files (git-aware).
3. Replace the import path in all callers (`search_files` for `sql_placeholders` to confirm
   none is left in `src/` and `tests/`; the XML fixture string in
   `tests/tools/test_ci_coverage_summary.py` is unrelated data — leave it).
4. Update the module docstring's first line of the test file only if it names the old path.
5. `tach.toml`: add
   ```toml
   [[modules]]
   path = "mcp_tools_sql.sql_ast"
   layer = "utilities"
   depends_on = []
   ```
   and add `{ path = "mcp_tools_sql.sql_ast" }` to `depends_on` of `count_tools`,
   `query_helpers`, `validation_tools`, `summarize`, `backends`. Remove now-unused
   `mcp_tools_sql.utils` edges only if tach reports them (`exact = false`, so leave them).
6. `.importlinter` layers contract: change the row
   `mcp_tools_sql.config` → `mcp_tools_sql.config | mcp_tools_sql.sql_ast`.

## ALGORITHM
None (mechanical move).

## DATA
Unchanged.

## Verification
- Compact diff (`mcp__mcp-workspace__git` diff, compact) shows only moves and import-line edits
  plus the two config edits.
- `run_lint_imports_check` passes (sql_ast imports nothing internal).
- `run_tach_check` passes.
- pylint, pytest (`-n auto`), mypy, ruff green; `run_format_code` before commit.

## Commit
`refactor(sql_ast): move sql_placeholders into new sql_ast package`

## LLM prompt
> Read `pr_info/steps/summary.md` and `pr_info/steps/step_1.md`. Implement step 1 exactly:
> a pure move of `src/mcp_tools_sql/utils/sql_placeholders.py` to
> `src/mcp_tools_sql/sql_ast/placeholders.py` plus its two test files into `tests/sql_ast/`,
> import-path updates, and the `tach.toml` / `.importlinter` edits listed. Change no logic.
> Use MCP tools only. Run pylint, pytest (`-n auto`), mypy, lint-imports, tach and ruff;
> all must pass. Format, then make one commit.
