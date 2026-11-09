# Step 3 — `SqlParseError` and one translation decorator

See `pr_info/steps/summary.md` for the overall design.

## Kind
Restructure (behaviour-preserving). TDD: tests first.

## WHERE
- `src/mcp_tools_sql/sql_ast/placeholders.py` — add `SqlParseError`, `translate_parse_errors`;
  decorate parsing functions; drop `ParseError`/`SqlglotError` from `__all__`.
- `src/mcp_tools_sql/sql_ast/summarize_queries.py` — decorate `validate_where`.
- `src/mcp_tools_sql/query_helpers.py` — catch `SqlParseError`.
- Render tails: `count_tools.py`, `validation_tools.py`, `summarize/tools.py`
  ("Unexpected error." branch) and `cli/commands/tool_dispatch.py` (generic tail).
- New test file `tests/sql_ast/test_parse_errors.py`.

## WHAT
```python
class SqlParseError(Exception):
    """SQL that sqlglot could not tokenize or parse; the SQL layer's only parse error."""

    def __init__(self, message: str, *, original_class: str) -> None: ...
    original_class: str          # sqlglot class name, e.g. "ParseError", "TokenError"

    @property
    def detail(self) -> str:      # single_line(str(self))
        ...

P = ParamSpec("P"); R = TypeVar("R")

def translate_parse_errors(fn: Callable[P, R]) -> Callable[P, R]:
    """Re-raise any SqlglotError from fn as SqlParseError (from exc)."""
```
Both live in `placeholders.py` (next to `single_line`, avoiding a new module and an
import cycle) and are listed in `__all__`.

## HOW
- Apply `@translate_parse_errors` to every public function in `sql_ast` that calls
  `sqlglot.parse` / `sqlglot.parse_one` directly: in `placeholders.py` e.g.
  `count_statements`, `extract_param_names`, `first_statement_kind`,
  `translate_named_to_qmark`, `substitute_named_with_literals`, `read_only_violation`,
  `keyword_absorption_violation`, `passthrough_source_violation`, `has_leading_cte`,
  `build_count_query` (check each with `search_files` for `parse`); in
  `summarize_queries.py`: `validate_where`.
- `basic_preflight`: `except SqlParseError as exc:` and render
  `f"Invalid SQL. {exc.original_class} (SQL parsed as {dialect}): {exc.detail}"` — byte-identical.
- `query_helpers.py`: import `SqlParseError` instead of `SqlglotError`; both `except` sites
  catch `SqlParseError`; `read_only_rejection` keeps `single_line(str(exc))` (identical text).
  Update the two docstrings to say `SqlParseError` (covers sqlglot's `TokenError` too).
- `placeholders.py`: keep `from sqlglot.errors import SqlglotError` (internal use);
  remove `ParseError` import if unused; remove `"ParseError"`, `"SqlglotError"` from `__all__`.
- Render tails, replace `type(exc).__name__` in the **"Unexpected error."** branch of
  `count_tools`, `validation_tools`, `summarize/tools.py`, and in `tool_dispatch.invoke_tool`'s
  generic `except Exception` message, with
  `getattr(exc, "original_class", type(exc).__name__)`. (The "Invalid SQL." branches follow in step 5.)
- Tests that imported `ParseError`/`SqlglotError` from the placeholders module: owner tests
  (`tests/sql_ast/**`) import them from `sqlglot.errors`; any `pytest.raises(ParseError)`
  around a decorated function becomes `pytest.raises(SqlParseError)` (assert
  `exc.original_class == "ParseError"` where the class was pinned).

## ALGORITHM
```
def wrapper(*args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except SqlglotError as exc:           # ParseError, TokenError, ...
        raise SqlParseError(str(exc), original_class=type(exc).__name__) from exc
```
`SqlParseError` raised by a nested decorated call is not a `SqlglotError`, so it passes through.

## DATA
`str(SqlParseError)` == `str(original sqlglot exception)`; `.original_class` str; `.detail` str.

## Tests first (`tests/sql_ast/test_parse_errors.py`)
- `SqlParseError("a\nb", original_class="ParseError")`: `str` is `"a\nb"`, `.detail == "a b"`,
  `isinstance(e, Exception)` and not `RuntimeError`/`ValueError`/`KeyError`/`TypeError`.
- Decorator: wrapped fn raising `sqlglot.errors.ParseError("x")` → `SqlParseError`,
  `original_class == "ParseError"`, `__cause__` is the original; `TokenError` → `"TokenError"`;
  `KeyError`/`ValueError` pass unchanged; return value passes through.
- Parametrized over the decorated public functions with `"SELECT 'unterminated"`
  (sqlglot `TokenError`): each raises `SqlParseError`, never a raw `SqlglotError`.
- `basic_preflight("SELECT 'x", None, "sqlite")` text unchanged (existing tests already pin it).
- `query_helpers.extract_sql_params("SELECT 'x")` → `set()`; `read_only_rejection` message unchanged.

## Verification
pylint, pytest (`-n auto`), mypy, lint-imports, ruff green; format; one commit.

## Commit
`refactor(sql_ast): translate sqlglot errors into SqlParseError`

## LLM prompt
> Read `pr_info/steps/summary.md` and `pr_info/steps/step_3.md`. Write the tests in
> `tests/sql_ast/test_parse_errors.py` first, then add `SqlParseError` and
> `translate_parse_errors` to `src/mcp_tools_sql/sql_ast/placeholders.py`, decorate the
> parsing functions, switch `basic_preflight` and `query_helpers` to `SqlParseError`, drop the
> sqlglot re-exports, and use `getattr(exc, "original_class", type(exc).__name__)` in the
> listed "Unexpected error." / `tool_dispatch` render tails. All user-visible text must stay
> byte-identical. Use MCP tools only. Run pylint, pytest (`-n auto`), mypy, lint-imports and
> ruff; all must pass. Format, then one commit.
