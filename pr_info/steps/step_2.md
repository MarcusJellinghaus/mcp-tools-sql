# Step 2 — `build_tool_fn` applies signature defaults

## LLM prompt
Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_2.md`.
TDD: add the failing tests first, then the fix. Run pylint, mypy, pytest (`-n auto`). One commit.

## Why
FastMCP passes every field, including defaults. LangChain (agent-workbench) passes
only the keys present in the input. Configured query bodies bind only the SQL
params present in `kwargs` (`query_helpers.py`, `stripped = {k: v for k, v in kwargs.items() if k in sql_params}`),
so an omitted optional `:param` (default `None`) fails at bind time. Filling
defaults once in `build_tool_fn` fixes every tool in one place.

## WHERE
- `src/mcp_tools_sql/tool_builder.py`
- `tests/test_tool_builder.py`

## WHAT
`build_tool_fn(name, sig_params, body, doc) -> Callable[..., Any]` — signature unchanged.

## ALGORITHM
```
sig = inspect.Signature(sig_params)
async def _tool_fn(**kwargs):
    bound = sig.bind(**kwargs)      # TypeError on unknown / missing required
    bound.apply_defaults()
    return await body(**bound.arguments)
_tool_fn.__signature__ = sig
```
Note: `bound.arguments` is keyed by parameter name; all tool params are
`POSITIONAL_OR_KEYWORD` or `KEYWORD_ONLY`, so passing it as `**kwargs` is exact.
`_UNSET` defaults pass through unchanged; update bodies already skip `_UNSET`.

## Tests (`tests/test_tool_builder.py`)
- Calling the built fn with only required kwargs forwards every parameter to the body, defaults filled (`None`, `_UNSET`, ints).
- Calling with all kwargs is unchanged.
- An unknown kwarg raises `TypeError`.
- Integration: build a query tool with an optional `:p` param (SQLite, `SELECT * FROM t WHERE (:p IS NULL OR name = :p)`) from `build_query_sig_params` + `build_query_body` + `build_tool_fn`, using the `sqlite_backend` helper. Calling `await fn()` with no kwargs returns the rows; before the fix it fails at bind time.

## DATA
No change.
