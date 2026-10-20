# Step 4: exit-code classifier and dispatch wrapper (`tool_dispatch.py`)

Read `pr_info/steps/summary.md` first, especially the exit-code
classification table. This step adds a standalone, unit-tested module that
wraps `Tool.fn_metadata.call_fn_with_arg_validation` and maps whatever
happens into one of the issue's exit codes. It is not yet wired into
`tool.py` (that's step 5).

**Precondition:** Step 2 is merged. If
`src/mcp_tools_sql/cli/commands/tool.py` does not exist yet, write one line
to `pr_info/.blocked.txt` and stop.

## WHERE

- `src/mcp_tools_sql/cli/commands/tool_dispatch.py` (new)
- `tests/cli/test_tool_dispatch.py` (new)

## WHAT

```python
EXIT_OK = 0
EXIT_CONFIG = 1
EXIT_REJECTED = 3
EXIT_BACKEND = 4

def classify_exception(exc: BaseException) -> int: ...

async def invoke_tool(tool: Tool, kwargs: dict[str, Any]) -> tuple[int, str]: ...
```

(`EXIT_ARGPARSE = 2` is not defined here — it never arises inside this
module; it's documented in `tool_help.EXIT_CODE_HELP` only.)

## HOW

- `_CONNECTION_EXC: tuple[type[BaseException], ...]` starts as
  `(RuntimeError, sqlite3.OperationalError, sqlite3.InterfaceError)`; guard-import
  `pyodbc` exactly like `validation_tools.py`/`count_tools.py` already do
  (`try: import pyodbc; _CONNECTION_EXC += (pyodbc.OperationalError,
  pyodbc.InterfaceError) except ImportError: pass`).
- `_REJECTED_EXC = (KeyError, TypeError, ValueError)`.
- `classify_exception`: `isinstance` check against `_CONNECTION_EXC` first
  (→ `EXIT_CONFIG`), then `_REJECTED_EXC` (→ `EXIT_REJECTED`), else
  `EXIT_BACKEND`. No explicit "execution" tuple is needed — every DB-API
  subclass not named above (`ProgrammingError`, `IntegrityError`,
  `DataError`, `NotSupportedError`, for both drivers) already falls through
  to the `EXIT_BACKEND` default.
- `invoke_tool`: calls
  `await tool.fn_metadata.call_fn_with_arg_validation(tool.fn, tool.is_async,
  kwargs, None)` — the exact step `Tool.run()` uses before it wraps results
  in `ToolError`, per `summary.md`. Catches `pydantic.ValidationError`
  first (→ `EXIT_REJECTED`, message = `str(exc)`), then any other
  `Exception` (→ `classify_exception(exc)`, message =
  `f"{type(exc).__name__}: {exc}"`). On success, returns
  `(EXIT_OK, str(result))`.

## ALGORITHM

```
classify_exception(exc):
    if isinstance(exc, _CONNECTION_EXC): return EXIT_CONFIG
    if isinstance(exc, _REJECTED_EXC): return EXIT_REJECTED
    return EXIT_BACKEND

invoke_tool(tool, kwargs):
    try:
        result = await tool.fn_metadata.call_fn_with_arg_validation(
            tool.fn, tool.is_async, kwargs, None)
        return EXIT_OK, str(result)
    except ValidationError as exc:
        return EXIT_REJECTED, str(exc)
    except Exception as exc:
        return classify_exception(exc), f"{type(exc).__name__}: {exc}"
```

## DATA

`invoke_tool` returns `tuple[int, str]` — an exit code and the text to
print, nothing else.

## Tests (write first)

`tests/cli/test_tool_dispatch.py` — build `Tool.from_function(fn)` over
tiny synthetic async functions, call `asyncio.run(invoke_tool(tool, kwargs))`:

1. A function that returns a plain string → `(0, "the string")`.
2. A function with an `Annotated[int, Field(ge=1)]` parameter, called with
   a violating value directly via `kwargs` (bypassing `argparse` entirely,
   simulating what a real dispatch would hit) → exit 3, message mentions
   the constraint.
3. A function that raises `RuntimeError("boom")` → exit 1.
4. A function that raises `sqlite3.OperationalError("unable to open
   database file")` → exit 1.
5. A function that raises `ValueError("at least one field value
   required")` (the exact `update_tools.py` wording) → exit 3.
6. A function that raises `sqlite3.ProgrammingError(...)` → exit 4.
7. A function that raises a generic `Exception("weird")` → exit 4 (default
   fallback).
8. `classify_exception` unit tests for each bucket directly, independent of
   `invoke_tool`.
9. Guard the `pyodbc`-specific branch with `pytest.mark.skipif` on
   `pyodbc` not being importable (it is not installed in this dev
   environment) rather than silently skipping; assert
   `classify_exception(pyodbc.OperationalError(...)) == EXIT_CONFIG` and
   `classify_exception(pyodbc.ProgrammingError(...)) == EXIT_BACKEND` when it is.

## Commit

One commit: the tests above, `tool_dispatch.py`, all checks passing.

## LLM prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_4.md`. Implement
> `src/mcp_tools_sql/cli/commands/tool_dispatch.py` exactly as specified:
> the exit-code constants, `classify_exception`, and `invoke_tool`. This
> module is tested standalone in this step — do not wire it into `tool.py`
> yet. Write `tests/cli/test_tool_dispatch.py` first, then the
> implementation. Run pylint, pytest, mypy, and ruff checks before
> committing.
