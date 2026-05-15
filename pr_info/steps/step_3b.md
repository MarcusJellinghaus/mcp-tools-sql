# Step 3b — MSSQL integration tests for `validate_sql`

Add MSSQL integration tests that cover the SHOWPLAN-on-isolated-connection path and the session-state containment guarantee. All tests are gated by the existing `mssql_integration` pytest marker and skip cleanly when `TEST_MSSQL_*` env vars are not set.

## WHERE

- `tests/test_validation_tools.py` — append MSSQL integration tests (marked `mssql_integration`).

## WHAT

### `tests/test_validation_tools.py` — MSSQL integration tests

All marked `@pytest.mark.mssql_integration`, using the `mssql_db` fixture from `tests/conftest.py`.

- [ ] Valid SELECT on `{schema}.customers` → `Valid.`
- [ ] Valid SELECT with `return_plan=True` → starts with `Valid.\nExecution plan:\n` and the plan text is non-empty.
- [ ] Invalid syntax (`SELEKT * FROM {schema}.customers`) → starts with `Invalid SQL. `.
- [ ] Unknown table (`SELECT * FROM {schema}.no_such_table`) → starts with `Invalid SQL. `.
- [ ] Unsupported param type — `validate_sql("SELECT :x", params={"x": set()})` → starts with `Invalid parameters. TypeError: ` (raised by `_sql_literal` during `substitute_named_with_literals`, before any SQL is sent).
- [ ] Non-finite float — `validate_sql("SELECT :x", params={"x": float('inf')})` → starts with `Invalid parameters. ValueError: ` (raised by `_sql_literal`).
- [ ] Valid UPDATE on `{schema}.customers` — `UPDATE {schema}.customers SET name = 'X' WHERE id = 999` → `Valid.` and customer 999 still does not exist afterwards (confirms EXPLAIN never executes on MSSQL).
- [ ] **Session-state containment** — after a `validate_sql` call that would otherwise mutate session state if not isolated (e.g. one that triggers SHOWPLAN on a SELECT and exits cleanly), `backend.execute_query("SELECT DB_NAME() AS db")` on the persistent backend returns the originally-configured database name (not `master`). This proves the isolated connection's lifecycle does not affect the persistent connection's session.

The `USE other_db` slipped-past-pre-flight scenario from the issue's test list is impossible by construction once pre-flight is in place (Step 2 catches it). The containment guarantee is therefore tested via the simpler invariant above: persistent connection's `DB_NAME()` is unchanged across a `validate_sql` cycle.

## HOW

- Reuse the existing `mssql_db` fixture (which yields an `MSSQLTestEnv(config, schema)` wrapper, not a bare backend) and the `mssql_integration` marker — no new conftest plumbing. The implementer constructs the backend in the test setup: `backend = MSSQLBackend(env.config)` and closes it in a `finally`.
- Tests instantiate the tool via `ValidationTools(backend, "mssql").register(mcp)` against a fresh `FastMCP`, then drive it through `create_connected_server_and_client_session` (matching Step 2's pattern). Alternatively, if Step 3a's server wiring is already committed by the time these run, the tests can go through the full `ToolServer` — either is acceptable; the manual-register path is simpler and avoids extra setup.
- The UPDATE-side-effect test guards against any future regression where MSSQL's SHOWPLAN path accidentally runs the statement. Pair it with a `SELECT COUNT(*) WHERE id = 999` before and after.
- The session-state containment test calls `validate_sql` once, then calls `backend.execute_query("SELECT DB_NAME() AS db")` and asserts the configured DB name is returned — proving the persistent connection's session was not touched by the isolated SHOWPLAN dance.

## ALGORITHM

```
For each MSSQL test:
    arrange: mssql_db fixture yields MSSQLTestEnv(config, schema)
             backend = MSSQLBackend(env.config); construct in setup; close in finally
             FastMCP + ValidationTools(backend, "mssql").register(mcp)
    act:     await client.call_tool("validate_sql", {...})
    assert:  verdict prefix / equality per the bullet list
```

## DATA

- No production-code changes in this step. Tests only.

## Tests checklist for this step

See the bullet list under WHAT.

## Commit & checks

Commit message: `test(mssql): add integration tests for validate_sql`.

Run before commit:
- `mcp__mcp-tools-py__run_format_code`
- `mcp__mcp-tools-py__run_pytest_check` with `extra_args=["-n", "auto"]`
- `mcp__mcp-tools-py__run_pylint_check`
- `mcp__mcp-tools-py__run_mypy_check`

All must pass. MSSQL integration tests skip cleanly when `TEST_MSSQL_*` env vars are not set (matching existing conftest behavior).

## LLM prompt for this step

> Implement Step 3b of issue #8 per `pr_info/steps/summary.md` and `pr_info/steps/step_3b.md`. Append MSSQL integration tests in `tests/test_validation_tools.py` covering valid SELECT, return_plan, syntax error, unknown table, unsupported-type, non-finite-float, valid UPDATE side-effect check, and DB_NAME() containment — all marked `@pytest.mark.mssql_integration`. Run format / pytest / pylint / mypy and commit as one commit.
