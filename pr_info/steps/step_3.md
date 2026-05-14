# Step 3 — Server wiring + MSSQL integration & isolation tests

Wire `ValidationTools` into `ToolServer._register_builtin_tools`, bump the startup `builtin_tools=<N>` counter, and add MSSQL integration tests that cover the SHOWPLAN-on-isolated-connection path and the session-state containment guarantee.

## WHERE

- `src/mcp_tools_sql/server.py` — register `ValidationTools`, add programmatic-builtin constant, bump counter.
- `tests/test_server.py` — assert `validate_sql` is among the registered tools.
- `tests/test_validation_tools.py` — append MSSQL integration tests (marked `mssql_integration`).

## WHAT

### `server.py` changes

```python
from mcp_tools_sql.validation_tools import ValidationTools

_PROGRAMMATIC_BUILTIN_TOOLS = 1  # validate_sql
```

In `ToolServer._register_builtin_tools`:
```python
def _register_builtin_tools(self) -> None:
    """Register schema-exploration tools from default_queries.toml and built-in validation tools."""
    SchemaTools(self._backend, self._backend_name).register(self._mcp)
    ValidationTools(self._backend, self._backend_name).register(self._mcp)
```

In `run_server`:
```python
n_builtin = len(load_default_queries()) + _PROGRAMMATIC_BUILTIN_TOOLS
```

### `tests/test_server.py` additions
- Test that after `ToolServer(...).mcp` registration via `_register_builtin_tools()` runs (call directly or via `.run()` route exercised by an existing helper), `validate_sql` appears in the listed MCP tools.

### `tests/test_validation_tools.py` — MSSQL integration tests

All marked `@pytest.mark.mssql_integration`, using the `mssql_db` fixture from `tests/conftest.py`.

- [ ] Valid SELECT on `{schema}.customers` → `Valid.`
- [ ] Valid SELECT with `return_plan=True` → starts with `Valid.\nExecution plan:\n` and the plan text is non-empty.
- [ ] Invalid syntax (`SELEKT * FROM {schema}.customers`) → starts with `Invalid SQL. `.
- [ ] Unknown table (`SELECT * FROM {schema}.no_such_table`) → starts with `Invalid SQL. `.
- [ ] Unsupported param type — `validate_sql("SELECT :x", params={"x": set()})` → starts with `Invalid parameters. TypeError: ` (raised by `_sql_literal` during `substitute_named_with_literals`, before any SQL is sent).
- [ ] Non-finite float — `validate_sql("SELECT :x", params={"x": float('inf')})` → starts with `Invalid parameters. ValueError: ` (raised by `_sql_literal`).
- [ ] **Session-state containment** — after a `validate_sql` call that would otherwise mutate session state if not isolated (e.g. one that triggers SHOWPLAN on a SELECT and exits cleanly), `backend.execute_query("SELECT DB_NAME() AS db")` on the persistent backend returns the originally-configured database name (not `master`). This proves the isolated connection's lifecycle does not affect the persistent connection's session.

The `USE other_db` slipped-past-pre-flight scenario from the issue's test list is impossible by construction once pre-flight is in place (Step 2 catches it). The containment guarantee is therefore tested via the simpler invariant above: persistent connection's `DB_NAME()` is unchanged across a `validate_sql` cycle.

## HOW

- Constructor for `ValidationTools` takes `(backend, backend_name)` — matches `QueryTools` / `UpdateTools` / `SchemaTools`.
- Update the existing `_register_builtin_tools` docstring to reflect that it now registers schema-exploration tools **and** built-in validation tools.
- The `n_builtin` log counter sums TOML-driven schema tools plus the programmatic-builtin constant; if a future step adds another programmatic built-in, bump the constant in one place.

## ALGORITHM

```
ToolServer._register_builtin_tools:
    SchemaTools(...).register(mcp)
    ValidationTools(...).register(mcp)

run_server:
    n_builtin = len(load_default_queries()) + _PROGRAMMATIC_BUILTIN_TOOLS
```

## DATA

- No return-value changes. `_PROGRAMMATIC_BUILTIN_TOOLS: int` constant added to `server.py`.

## Tests checklist for this step

### `tests/test_server.py`
- [ ] `validate_sql` is among the names listed by `mcp.list_tools()` after `_register_builtin_tools()` runs.
- [ ] `builtin_tools=<N>` log line emitted by `run_server` reflects `len(load_default_queries()) + 1` (verify via `caplog`).

### `tests/test_validation_tools.py` — MSSQL integration
See the bullet list under WHAT.

## Commit & checks

Commit message: `feat(server): wire validate_sql into ToolServer`.

Run before commit:
- `mcp__mcp-tools-py__run_format_code`
- `mcp__mcp-tools-py__run_pytest_check` with `extra_args=["-n", "auto"]`
- `mcp__mcp-tools-py__run_pylint_check`
- `mcp__mcp-tools-py__run_mypy_check`

All must pass. MSSQL integration tests skip cleanly when `TEST_MSSQL_*` env vars are not set (matching existing conftest behavior).

## LLM prompt for this step

> Implement Step 3 of issue #8 per `pr_info/steps/summary.md` and `pr_info/steps/step_3.md`. In `src/mcp_tools_sql/server.py`: import `ValidationTools`, add `_PROGRAMMATIC_BUILTIN_TOOLS = 1` constant, register `ValidationTools(self._backend, self._backend_name).register(self._mcp)` after `SchemaTools` in `_register_builtin_tools`, and update `n_builtin` in `run_server` to include the constant. Update the `_register_builtin_tools` docstring. Add a `validate_sql`-registration test in `tests/test_server.py` (assert it appears in `mcp.list_tools()` and the `builtin_tools` log counter increments). Append MSSQL integration tests in `tests/test_validation_tools.py` covering valid SELECT, return_plan, syntax error, unknown table, unsupported-type, non-finite-float, and DB_NAME() containment — all marked `@pytest.mark.mssql_integration`. Run format / pytest / pylint / mypy and commit as one commit.
