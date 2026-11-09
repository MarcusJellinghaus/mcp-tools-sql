# Step 5 — Neutral backend exceptions; upper layers catch them (additively)

See `pr_info/steps/summary.md` for the overall design.

## Kind
Restructure. TDD: tests first. Additive: raw driver types stay in the catch tuples until step 9,
so every step stays green while backends start translating (steps 6–7).

## WHERE
- `src/mcp_tools_sql/backends/base.py` — `BackendError`, `BackendConnectionError`, `wrap_driver_error`.
- `src/mcp_tools_sql/count_tools.py`, `validation_tools.py`, `summarize/source.py`,
  `summarize/tools.py`, `cli/commands/tool_dispatch.py`.
- `tach.toml` — `mcp_tools_sql.cli.commands` gains `{ path = "mcp_tools_sql.backends" }`.
- Tests: new `tests/backends/test_base_errors.py`; additions in `tests/test_count_tools.py`,
  `tests/test_validation_tools.py`, `tests/summarize/test_tools.py`, `tests/cli/test_tool_dispatch.py`.

## WHAT
```python
class BackendError(Exception):
    """A database driver error translated at the backend boundary."""
    def __init__(self, *args: object, original_class: str) -> None: ...
    original_class: str

class BackendConnectionError(BackendError):
    """Driver OperationalError / InterfaceError (connection-shaped)."""

def wrap_driver_error(
    exc: BaseException, connection_types: tuple[type[BaseException], ...]
) -> BackendError:
    """Build the neutral exception for a driver exception, keeping its args and class name."""
```
`QueryTimeoutError` is unchanged and is **not** a `BackendError` subclass.

## HOW
- `count_tools.py` / `validation_tools.py`: `_INVALID_SQL_EXC = (BackendError, sqlite3.Error, *_PYODBC_ERROR)`.
- `summarize/source.py`: `INVALID_SQL_EXC = (BackendError, sqlite3.Error, *_PYODBC_ERROR)`.
- The three "Invalid SQL." branches render
  `f"Invalid SQL. {getattr(exc, 'original_class', type(exc).__name__)}: {exc}"`.
- `tool_dispatch.py`: add `BackendConnectionError` to both `_CONNECTION_EXC` variants
  (import from `mcp_tools_sql.backends.base`). Generic tail already uses `original_class` (step 3).
- Import `BackendError` / `BackendConnectionError` from `mcp_tools_sql.backends.base` (runtime import,
  not `TYPE_CHECKING`).

## ALGORITHM
```
def wrap_driver_error(exc, connection_types):
    cls = BackendConnectionError if isinstance(exc, connection_types) else BackendError
    return cls(*exc.args, original_class=type(exc).__name__)
```
Callers do `raise wrap_driver_error(exc, ...) from exc`.

## DATA
`str(wrapped) == str(exc)` for single- and multi-arg drivers (pyodbc uses `(sqlstate, message)`).

## Tests first
`tests/backends/test_base_errors.py` (owner test, may import sqlite3):
- `wrap_driver_error(sqlite3.OperationalError("no such table: t"), (sqlite3.OperationalError, sqlite3.InterfaceError))`
  → `BackendConnectionError`, `str == "no such table: t"`, `original_class == "OperationalError"`.
- `sqlite3.ProgrammingError` → plain `BackendError` (not connection).
- Multi-arg exception `Err("42S02", "[42S02] msg")` → `str` equals `str` of the original, `.args` equal.
- `connection_types=()` → plain `BackendError`.
- `BackendError` is not a subclass of `RuntimeError`, `ValueError`, `KeyError`, `TypeError`;
  `QueryTimeoutError` is not a subclass of `BackendError`.
Upper layers (mock backend raising `BackendConnectionError("no such table: x", original_class="OperationalError")`):
- `count_records` → `"Invalid SQL. OperationalError: no such table: x"`.
- `validate_sql` (mock `explain`) → same text.
- `summarize_columns` → same text (`+ LOB_HINT` rules unchanged).
- `classify_exception(BackendConnectionError(..))` → `EXIT_CONFIG`; `BackendError(..., original_class="ProgrammingError")` → `EXIT_BACKEND`;
  `invoke_tool` message `"ProgrammingError: <msg>"`.

## Verification
pylint, pytest (`-n auto`), mypy, lint-imports, tach, ruff green; format; one commit.

## Commit
`refactor(backends): add neutral BackendError/BackendConnectionError`

## LLM prompt
> Read `pr_info/steps/summary.md` and `pr_info/steps/step_5.md`. Write the tests listed first,
> then add `BackendError`, `BackendConnectionError` and `wrap_driver_error` to
> `src/mcp_tools_sql/backends/base.py`, and let `count_tools`, `validation_tools`,
> `summarize/source.py`, `summarize/tools.py` and `cli/commands/tool_dispatch.py` catch / classify
> them in addition to the raw driver types (do not remove the raw types yet). Render via
> `getattr(exc, "original_class", type(exc).__name__)`. Add the `cli.commands -> backends` edge
> in `tach.toml`. Use MCP tools only. Run pylint, pytest (`-n auto`), mypy, lint-imports, tach
> and ruff; all must pass. Format, then one commit.
