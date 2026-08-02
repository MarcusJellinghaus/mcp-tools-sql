# Step 1 — Prereq: dialect-aware placeholder translation

See `pr_info/steps/summary.md` → "Prerequisite bug fixes" (item 1).

## WHERE
- `src/mcp_tools_sql/utils/sql_placeholders.py`
- `src/mcp_tools_sql/backends/mssql.py`
- `src/mcp_tools_sql/validation_tools.py`
- Tests: `tests/test_sql_placeholders.py`, `tests/backends/test_mssql.py`

## WHAT
Add a `dialect` parameter to both functions, applied to **parse and render**:

```python
def translate_named_to_qmark(sql: str, dialect: str | None = None) -> tuple[str, list[str]]: ...
def substitute_named_with_literals(sql: str, params: dict[str, Any], dialect: str | None = None) -> str: ...
```

Thread the backend dialect from call sites:
- `MSSQLBackend._params_for_pyodbc` → `translate_named_to_qmark(sql, "tsql")`
- `MSSQLBackend.explain` → `substitute_named_with_literals(sql, params, "tsql")`
- `validation_tools._explain` (MSSQL branch) → `substitute_named_with_literals(sql, params, "tsql")`

## HOW
Inside both functions replace `_statements(sql)` with `_statements(sql, dialect)`
and `stmt.sql()` with `stmt.sql(dialect=dialect)`. Default `dialect=None`
preserves the current dialect-neutral behaviour for existing callers/tests.

## ALGORITHM (both functions)
```
for stmt in _statements(sql, dialect):        # parse under dialect
    for ph in _named_placeholders(stmt):
        <replace ph as before>
    rendered.append(stmt.sql(dialect=dialect)) # render under dialect
return "; ".join(rendered), names             # (names only for translate_*)
```

## DATA
Unchanged return types. `translate_named_to_qmark` → `(sql, ordered_names)`;
`substitute_named_with_literals` → `str`.

## TESTS (write first)
Parameterised over `dialect="tsql"`, asserting the **rendered text round-trips**
(a "no exception" assertion would miss the silent-rewrite bug):
- `SELECT [id], [name] FROM dbo.[orders] WHERE [id] = :id` keeps `[...]` quoting
  after `translate_named_to_qmark(..., "tsql")` (no `ARRAY(...)`).
- `SELECT * FROM [orders] WHERE id = :id` parses without `ParseError` under tsql.
- `substitute_named_with_literals("... [id] = :id", {"id": 5}, "tsql")` renders
  `[id] = 5` (bracket quoting preserved, literal substituted).
- Existing `dialect=None` cases still pass (regression).
- `test_mssql.py`: `_params_for_pyodbc` on bracketed SQL yields bracketed `?` SQL.

## LLM PROMPT
> Implement Step 1 from `pr_info/steps/step_1.md` (context in
> `pr_info/steps/summary.md`). Add a `dialect: str | None = None` parameter to
> `translate_named_to_qmark` and `substitute_named_with_literals` in
> `utils/sql_placeholders.py`, applying it to both `_statements(sql, dialect)` and
> `stmt.sql(dialect=dialect)`. Thread `"tsql"` from `mssql.py`
> (`_params_for_pyodbc`, `explain`) and from `validation_tools._explain`. Write the
> round-trip regression tests first. Run `mcp__tools-py__run_pylint_check`,
> `mcp__tools-py__run_pytest_check` (with `-n auto` and the unit-test marker
> exclusions from CLAUDE.md), and `mcp__tools-py__run_mypy_check`; all must pass.
> One commit.
