# Step 2 — Move `summarize/sql.py` → `sql_ast/summarize_queries.py`; split the readonly test (move step)

See `pr_info/steps/summary.md` for the overall design.

## Kind
Pure move. No logic changes.

## WHERE
- `src/mcp_tools_sql/summarize/sql.py` → `src/mcp_tools_sql/sql_ast/summarize_queries.py`
- `tests/summarize/test_sql.py` → `tests/sql_ast/test_summarize_queries.py`
- `tests/test_query_tools_readonly.py` → split; new `tests/sql_ast/test_tokenizer_premises.py`

## WHAT
1. Module move. Update imports `mcp_tools_sql.summarize.sql` →
   `mcp_tools_sql.sql_ast.summarize_queries` in:
   `summarize/render.py`, `summarize/source.py`, `summarize/tools.py` (also its
   module docstring mention of ``summarize/sql.py``), and tests
   `summarize/test_render.py`, `summarize/test_render_clamp.py`, `summarize/test_source.py`,
   `summarize/test_tools.py`, the moved `test_summarize_queries.py` (many function-local imports).
   Inside the moved module, its import of `mcp_tools_sql.sql_ast.placeholders` stays absolute.
2. Test split of `tests/test_query_tools_readonly.py::test_token_error_is_a_rejection_message`:
   - The sqlglot premise part moves to `tests/sql_ast/test_tokenizer_premises.py` as
     `test_token_error_is_sibling_of_parse_error` with the same parametrization:
     ```python
     assert issubclass(TokenError, SqlglotError)
     assert not issubclass(TokenError, ParseError)
     with pytest.raises(TokenError):
         <the same raising call as today>
     ```
     importing `TokenError`, `ParseError`, `SqlglotError` from `sqlglot.errors`
     (owner test — allowed).
   - The part that asserts `read_only_rejection(...)` returns a message stays in
     `tests/test_query_tools_readonly.py`, renamed `test_untokenizable_sql_is_a_rejection_message`,
     without any sqlglot import. Remove the `from sqlglot.errors import TokenError` line
     and the `ParseError`/`SqlglotError` names from its placeholders import if no longer used.

## HOW
`mcp__mcp-tools-py__move_module` cannot rename; use `mcp__mcp-workspace__move_file`, then fix
imports (`search_files` for `summarize.sql` / `summarize/sql` to confirm none left).
`tach.toml` needs no change (`summarize` already depends on `sql_ast` from step 1).

## ALGORITHM
None.

## DATA
Unchanged.

## Verification
- Compact diff shows moves, import edits and the test split only.
- Test count unchanged (one test split into two counts as +1 — acceptable).
- pylint, pytest (`-n auto`), mypy, lint-imports, ruff green; format before commit.

## Commit
`refactor(sql_ast): move summarize SQL builders into sql_ast`

## LLM prompt
> Read `pr_info/steps/summary.md` and `pr_info/steps/step_2.md`. Implement step 2: move
> `src/mcp_tools_sql/summarize/sql.py` to `src/mcp_tools_sql/sql_ast/summarize_queries.py`
> and `tests/summarize/test_sql.py` to `tests/sql_ast/test_summarize_queries.py`, update
> imports, and split the sqlglot premise assertions out of
> `tests/test_query_tools_readonly.py` into `tests/sql_ast/test_tokenizer_premises.py` as
> described. No logic changes. Use MCP tools only. Run pylint, pytest (`-n auto`), mypy,
> lint-imports and ruff; all must pass. Format, then one commit.
