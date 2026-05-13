# Step 5 — MSSQL integration tests (real pyodbc, gated by marker)

## Goal

Exercise the full `MSSQLBackend` against a real SQL Server (the CI
`mssql-integration` job already provides one). Gated behind
`@pytest.mark.mssql_integration` so unit-test runs skip it.

## WHERE

| Action | Path |
|---|---|
| Modify | `tests/conftest.py` (add `mssql_db` fixture) |
| Modify | `tests/backends/test_mssql.py` (add `TestMSSQLIntegration` class) |

## WHAT

### `tests/conftest.py` — new fixture

```python
@pytest.fixture
def mssql_db() -> Generator[ConnectionConfig, None, None]: ...
```

- Reads `TEST_MSSQL_HOST`, `TEST_MSSQL_PORT`, `TEST_MSSQL_USER`,
  `TEST_MSSQL_PASSWORD`, optional `TEST_MSSQL_DB` (default `master`).
- If any required var is missing, `pytest.skip("TEST_MSSQL_* not set")`.
- Builds a `ConnectionConfig(backend="mssql", trust_server_certificate=True,
  encrypt=True, …)`.
- Opens a temporary `MSSQLBackend`, creates `customers` and `orders` test
  tables in a unique schema (`test_<uuid8>`), seeds the same rows used by
  the SQLite fixture, yields the `ConnectionConfig`, then drops the schema
  in teardown.

### `tests/backends/test_mssql.py` — new integration class

```python
@pytest.mark.mssql_integration
class TestMSSQLIntegration:
    def test_execute_query_real_round_trip(mssql_db): ...
    def test_execute_update_real_round_trip(mssql_db): ...
    def test_explain_returns_text_plan(mssql_db): ...
    def test_connect_close_lifecycle(mssql_db): ...
```

## HOW

- `mssql_db` builds a one-off `MSSQLBackend` for setup/teardown using its
  own short-lived connection so the yielded config can be re-used by the
  test, which constructs its own `MSSQLBackend`.
- Schema isolation: `CREATE SCHEMA test_<uuid8>` then qualify table names
  as `[<schema>].[customers]` etc. Drop schema + tables in teardown.
- Fixture must be **idempotent on failure**: wrap teardown in `try/except`
  so test errors don't mask the original failure.

## ALGORITHM — fixture

```
def mssql_db():
    for var in REQUIRED: ensure os.environ has it, else pytest.skip
    cfg_admin = ConnectionConfig(..., trust_server_certificate=True)
    schema = f"test_{uuid.uuid4().hex[:8]}"
    with MSSQLBackend(cfg_admin) as b:
        b.execute_update(f"CREATE SCHEMA {schema}")
        b.execute_update(f"CREATE TABLE {schema}.customers (id INT PRIMARY KEY, name NVARCHAR(50), country NVARCHAR(50))")
        b.execute_update(f"CREATE TABLE {schema}.orders (id INT PRIMARY KEY, customer_id INT, status NVARCHAR(20), total FLOAT)")
        for row in SEED_CUSTOMERS: b.execute_update("INSERT INTO ...", row)
        for row in SEED_ORDERS:    b.execute_update("INSERT INTO ...", row)
    cfg_admin._test_schema = schema     # attach for test to read
    try:
        yield cfg_admin
    finally:
        with MSSQLBackend(cfg_admin) as b:
            try: b.execute_update(f"DROP TABLE {schema}.orders")
            except Exception: pass
            try: b.execute_update(f"DROP TABLE {schema}.customers")
            except Exception: pass
            try: b.execute_update(f"DROP SCHEMA {schema}")
            except Exception: pass
```

Simpler alternative: instead of attaching `_test_schema`, return a small
dataclass `MSSQLTestEnv(config, schema)`. Either is fine — pick whichever
is cleaner.

## DATA

- Seed rows (must match the SQLite fixture in `tests/conftest.py`):
  - customers: `(1, 'Bank A', 'Germany')`, `(2, 'Bank B', 'France')`
  - orders: `(1, 1, 'pending', 1000.0)`, `(2, 1, 'shipped', 2500.0)`,
    `(3, 2, 'pending', 750.0)`

## Tests

```python
@pytest.mark.mssql_integration
class TestMSSQLIntegration:
    def test_execute_query_real_round_trip(mssql_db):
        with MSSQLBackend(mssql_db.config) as b:
            rows = b.execute_query(
                f"SELECT name FROM {mssql_db.schema}.customers "
                "WHERE country = :country", {"country": "Germany"})
            assert rows == [{"name": "Bank A"}]

    def test_execute_update_real_round_trip(mssql_db):
        with MSSQLBackend(mssql_db.config) as b:
            n = b.execute_update(
                f"INSERT INTO {mssql_db.schema}.customers VALUES "
                "(:id, :name, :country)",
                {"id": 99, "name": "Bank Z", "country": "Spain"})
            assert n == 1

    def test_explain_returns_text_plan(mssql_db):
        with MSSQLBackend(mssql_db.config) as b:
            plan = b.explain(
                f"SELECT * FROM {mssql_db.schema}.customers WHERE id = :id",
                {"id": 1})
            assert isinstance(plan, str) and len(plan) > 0

    def test_connect_close_lifecycle(mssql_db):
        b = MSSQLBackend(mssql_db.config)
        b.connect(); b.connect()         # idempotent
        b.execute_query("SELECT 1 AS one")
        b.close(); b.close()             # idempotent
        with pytest.raises(RuntimeError):
            b.execute_query("SELECT 1")
```

## Checks

- `mcp__tools-py__run_pylint_check`
- `mcp__tools-py__run_mypy_check`
- `mcp__tools-py__run_pytest_check(extra_args=["-n", "auto", "-m", "not git_integration and not claude_cli_integration and not claude_api_integration and not formatter_integration and not github_integration and not langchain_integration"])`
  - integration tests are **excluded** from this default run.
- Optional, requires running SQL Server + `TEST_MSSQL_*` env vars:
  `mcp__tools-py__run_pytest_check(extra_args=["-n", "auto"], markers=["mssql_integration"])`
- `./tools/format_all.sh`
- Single commit.

## LLM Prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_5.md`. Add the
> `mssql_db` fixture to `tests/conftest.py` (skip when `TEST_MSSQL_*` env
> vars are missing, schema-isolated setup + teardown) and add the
> `TestMSSQLIntegration` class to `tests/backends/test_mssql.py` behind
> `@pytest.mark.mssql_integration`. The default pytest run (with the
> CLAUDE.md exclusion pattern) must not collect or fail on these tests when
> the env vars are unset. Run pylint, mypy, pytest via MCP tools per
> CLAUDE.md after every edit. End with a single commit.
