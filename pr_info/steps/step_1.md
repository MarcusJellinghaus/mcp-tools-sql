# Step 1 — Parsing foundation: dependency swap + reimplement placeholder helpers on sqlglot

> Read `pr_info/steps/summary.md` first. This step replaces `sqlparse` with
> `sqlglot` and reimplements the three placeholder helpers on the sqlglot AST.
> It is the foundation every later step builds on (the "make-or-break"
> placeholder round-trip spike is verified here by the tests themselves).

## WHERE
- `pyproject.toml`
- `src/mcp_tools_sql/utils/sql_placeholders.py` (reimplemented)
- `tests/test_sql_placeholders.py` (updated)

## WHAT (public signatures — unchanged, behavior re-based on sqlglot)
```python
def extract_param_names(sql: str) -> set[str]: ...
def translate_named_to_qmark(sql: str) -> tuple[str, list[str]]: ...
def substitute_named_with_literals(sql: str, params: dict[str, Any]) -> str: ...
# kept: _sql_literal(value) -> str  (Python value -> SQL literal; unchanged logic)
```

## HOW (integration)
- `pyproject.toml`: in `dependencies`, replace `"sqlparse>=0.5"` with
  `"sqlglot>=25"`. Remove the `[[tool.mypy.overrides]]` block for
  `module = ["sqlparse", "sqlparse.*"]`. (`sqlglot` ships type hints; no
  override needed. If mypy complains, add a `sqlglot.*` override instead.)
- Imports in `sql_placeholders.py`:
  `import sqlglot`, `from sqlglot import exp`. Drop all `sqlparse` imports.
- Existing consumers keep working unchanged via these signatures:
  `query_helpers.extract_sql_params`, `backends/mssql.py`
  (`translate_named_to_qmark`, `substitute_named_with_literals`).

## ALGORITHM (core logic)
```
# Verify in the spike: :name parses to a placeholder node (likely exp.Placeholder
# with .name == "name"; ? parses to a placeholder with empty name). Adapt below
# to the observed node type.

def _placeholder_nodes(expr):           # DFS order == render order
    return [n for n in expr.find_all(exp.Placeholder) if n.name]   # named only

extract_param_names(sql):
    return {n.name for stmt in sqlglot.parse(sql) if stmt
                    for n in _placeholder_nodes(stmt)}

translate_named_to_qmark(sql):          # render each stmt, names in order
    for each parsed stmt: collect names in order; replace named placeholder
        nodes with anonymous "?" placeholder; render with stmt.sql()
    return rendered_joined, names

substitute_named_with_literals(sql, params):
    for each parsed stmt: replace each named placeholder node with a parsed
        literal of _sql_literal(params[name]); render with stmt.sql()
```
Notes:
- sqlglot ignores `:name` inside string literals / comments automatically (they
  are not placeholder nodes) — preserves the "ignore quoted/comment" guarantee.
- A missing key raises `KeyError` via `params[name]`; non-finite floats /
  unsupported types still raise from `_sql_literal` (unchanged).
- Use `exp.Placeholder(this=name)` to recreate named placeholders if needed.

## DATA
- `extract_param_names` → `set[str]` (names, no leading `:`).
- `translate_named_to_qmark` → `(str, list[str])`; the str uses `?` markers,
  the list is the ordered names (duplicates preserved).
- `substitute_named_with_literals` → `str` with literals inlined.

## TDD / TESTS (`tests/test_sql_placeholders.py`)
Write/adjust first, then implement until green:
- Keep behavioral intent of every existing case (extract ignores
  string/comment/double-quote; repeated names; multi-statement; no placeholders;
  `?` translation order; literal rendering for int/float/bool/str/None/date/
  datetime/Decimal/bytes; quote-escaping; KeyError; non-finite ValueError;
  unsupported TypeError).
- **Expect rendered-text churn**: sqlglot reformats and drops comments. Update
  exact-string assertions to match sqlglot's render (e.g. the
  `"-- :b"` comment cases will no longer keep the comment; assert the
  semantically-correct rendered output and the correct names list instead).
- Add a focused **round-trip test**: parse `SELECT :a`, render via the helper,
  confirm `extract_param_names` still returns `{"a"}` and that the rendered text
  contains a bindable placeholder.
- Add a **multi-placeholder ordered round-trip** test (e.g.
  `SELECT * FROM t WHERE a = :x AND b = :y`): assert `translate_named_to_qmark`
  returns `["x", "y"]` in that exact order — i.e. the `:name`→`?` positional
  order is preserved (the `find_all` traversal order matches the render order).

## DONE WHEN
- `pyproject.toml` no longer references `sqlparse`; `sqlglot` present.
- The sqlglot placeholder **node type** (`exp.Placeholder` vs `exp.Parameter`)
  is **empirically confirmed and asserted by a test** — the make-or-break spike
  is gated, not merely mentioned (a test parses `:name` and asserts the concrete
  node class / `.name`).
- `run_pylint_check`, `run_mypy_check`, `run_pytest_check` (unit subset) all pass.
- Single commit: pyproject + sql_placeholders.py + test_sql_placeholders.py.

## LLM PROMPT
> Implement Step 1 of `pr_info/steps/summary.md` (`pr_info/steps/step_1.md`).
> Swap `sqlparse` for `sqlglot` in `pyproject.toml` (remove the sqlparse mypy
> override). Reimplement `extract_param_names`, `translate_named_to_qmark`, and
> `substitute_named_with_literals` in
> `src/mcp_tools_sql/utils/sql_placeholders.py` on the sqlglot AST, keeping the
> exact public signatures and the "ignore placeholders in strings/comments"
> guarantee. First confirm sqlglot's placeholder node type empirically, then
> update `tests/test_sql_placeholders.py` (TDD) to the new sqlglot-rendered
> output while preserving each test's intent; add a `:name` round-trip test.
> Use MCP tools only. Run `mcp__tools-py__run_pylint_check`,
> `mcp__tools-py__run_mypy_check`, and `mcp__tools-py__run_pytest_check`
> (`extra_args=["-n","auto","-m","not git_integration and not
> claude_cli_integration and not claude_api_integration and not
> formatter_integration and not github_integration and not
> langchain_integration"]`) until all pass. Produce exactly one commit.
