# Step 8 — `verify` M2: QUERIES section

**Reference**: [summary.md](./summary.md) — section "`verify` M1 / M2 sections"
**Commit**: 8 of 10
**Goal**: Per-query validation: SQL valid via EXPLAIN, params well-formed, max_rows set.

> **Decisions for this step**:
> - **Promote `schema_tools._extract_sql_params` → public `extract_sql_params`** (drop the leading underscore). Update all internal call sites in `schema_tools` accordingly. `verify_queries` imports the public name. (Rationale: a second module — verify — now needs this helper; promoting it formalizes the API surface instead of reaching into a private name.)
> - **SQLite EXPLAIN with parameters**: `_check_sql_explain` builds a dummy params dict from `params.keys()`, mapping each name to a type-appropriate placeholder value (`""` for `str`, `0` for `int`, `0.0` for `float`, `datetime.datetime(2000, 1, 1)` for `datetime`). It then calls `backend.explain(sql, dummy_params)`. SQLite's `EXPLAIN QUERY PLAN` requires bound values to compile parameterized SQL. Document this clearly in `_check_sql_explain`'s docstring.
> - **MSSQL EXPLAIN scope kept as-is**: `backend.explain(sql)` is the only call. The MSSQL backend's `explain()` currently raises `NotImplementedError`; verify reports `[ERR]` with the exception message — clean and readable. No `SET SHOWPLAN_TEXT ON` / SHOWPLAN code lands in this PR; that ships with the MSSQL backend itself (issues #5/#6).

---

## WHERE

Modify:
- `src/mcp_tools_sql/cli/commands/verify.py`
- `src/mcp_tools_sql/backends/base.py` — widen `DatabaseBackend.explain` signature
- `src/mcp_tools_sql/backends/sqlite.py` — widen `SQLiteBackend.explain` signature; bind `params or {}` to the cursor
- `tests/cli/test_verify.py` — extend

---

## WHAT — Backend signature widening

`DatabaseBackend.explain` and `SQLiteBackend.explain` currently accept only `sql`. `_check_sql_explain` (below) needs to pass a dummy params dict when calling `backend.explain(sql, dummy_params)` for SQLite — the current signature won't compile. Widen both:

```python
# src/mcp_tools_sql/backends/base.py
class DatabaseBackend(ABC):
    @abstractmethod
    def explain(self, sql: str, params: dict[str, Any] | None = None) -> str: ...

# src/mcp_tools_sql/backends/sqlite.py
class SQLiteBackend(DatabaseBackend):
    def explain(self, sql: str, params: dict[str, Any] | None = None) -> str:
        # Pass params or {} to the cursor — SQLite's EXPLAIN QUERY PLAN requires bound
        # values to compile parameterized SQL (see Decisions.md: SQLite EXPLAIN with parameters).
        ...
```

This widening is **backwards-compatible** — the new `params` argument defaults to `None`, so existing callers of `backend.explain(sql)` continue to work unchanged. Only `_check_sql_explain` for SQLite passes the second arg.

---

## WHAT — Function signatures

```python
def verify_queries(
    queries: dict[str, QueryConfig],
    backend_name: str,
    backend: DatabaseBackend,
) -> dict[str, Any]:
    """
    For each query <name>, emit three rows:
      <name>.sql:        EXPLAIN works
      <name>.params:     :name in SQL <-> config params consistent + types in allowed set
      <name>.max_rows:   max_rows > 0
    """


_VALID_PARAM_TYPES = {"str", "int", "float", "datetime"}
_EXPLAIN_PREFIX = {
    "sqlite": "EXPLAIN QUERY PLAN",
    "postgresql": "EXPLAIN",
    "mssql": "SET SHOWPLAN_TEXT ON;",  # special handling required
}


def _check_sql_explain(
    sql: str,
    params: dict[str, QueryParamConfig],
    backend_name: str,
    backend: DatabaseBackend,
) -> tuple[bool, str]:
    """Return (ok, error_message).

    For SQLite, builds a dummy params dict (keys from `params`, values placeholders
    chosen per declared type: '' / 0 / 0.0 / datetime(2000,1,1)) and passes it to
    backend.explain(sql, dummy_params) so EXPLAIN QUERY PLAN can compile the
    parameterized SQL. For MSSQL, calls backend.explain(sql) — currently raises
    NotImplementedError, so we report [ERR] with the exception message; that's the
    intended behavior until the MSSQL backend lands (issues #5/#6).
    """


def _check_params_well_formed(
    sql: str, params: dict[str, QueryParamConfig]
) -> tuple[bool, str]:
    """:name in SQL ↔ config params + each type ∈ _VALID_PARAM_TYPES."""
```

---

## HOW — `_check_sql_explain` per backend

### sqlite
```python
backend.execute_query(f"EXPLAIN QUERY PLAN {sql}")
```
On `sqlite3.OperationalError` etc. → ok=False with `str(exc)`.

### postgresql
```python
backend.execute_query(f"EXPLAIN {sql}")
```

### mssql
SQL Server's `SET SHOWPLAN_TEXT ON` is a session-level toggle: subsequent statements return their plan instead of executing. Use a separate execution path:
```python
# Best-effort; if SHOWPLAN_TEXT isn't reachable, fall back to wrapping in a NOEXEC pattern.
try:
    backend._connection.execute("SET SHOWPLAN_TEXT ON")
    backend.execute_query(sql)
finally:
    backend._connection.execute("SET SHOWPLAN_TEXT OFF")
```

(Reaching into `_connection` is acceptable here because verify is a backend-aware diagnostic; alternative is a small `backend.explain(sql)` call which already exists — `DatabaseBackend.explain` is on the ABC. Re-use that instead, falling back to the per-backend logic only if `explain()` raises `NotImplementedError`.) **Prefer `backend.explain(sql)` first**, then fall back if needed.

Actually since `DatabaseBackend.explain(sql)` already exists as the ABC method, `_check_sql_explain` can collapse to:
```python
try:
    plan = backend.explain(sql)
    return True, ""
except Exception as exc:
    return False, str(exc)
```

For MSSQL, the existing `explain()` is `NotImplementedError`. Until MSSQL backend is built (out of scope per #5/#6), MSSQL queries report `[ERR]` with a clear message. That's the issue's mandate ("unimplemented backend = regular `[ERR]`"). So this collapses neatly.

### Final algorithm
```python
_DUMMY_BY_TYPE = {
    "str": "",
    "int": 0,
    "float": 0.0,
    "datetime": datetime.datetime(2000, 1, 1),
}


def _check_sql_explain(sql, params, backend_name, backend) -> tuple[bool, str]:
    try:
        if backend_name == "sqlite":
            dummy = {name: _DUMMY_BY_TYPE.get(p.type, "") for name, p in params.items()}
            backend.explain(sql, dummy)
        else:
            # mssql / postgresql / others — explain() either supports it or raises
            # NotImplementedError; in either case the surface is the same: we report
            # the outcome straight from the backend.
            backend.explain(sql)
        return True, ""
    except Exception as exc:
        return False, str(exc)
```

---

## HOW — `_check_params_well_formed`

Re-use `extract_sql_params` from `schema_tools` (promoted from the previously private `_extract_sql_params` in this step — drop the leading underscore and update internal call sites). Verify is the second consumer, so the public API rename is the right call.

```python
from mcp_tools_sql.schema_tools import extract_sql_params

def _check_params_well_formed(sql, params):
    sql_names = extract_sql_params(sql)
    config_names = set(params.keys())

    missing_in_config = sql_names - config_names
    extra_in_config = config_names - sql_names
    bad_types = [(n, p.type) for n, p in params.items() if p.type not in _VALID_PARAM_TYPES]

    errors: list[str] = []
    if missing_in_config:
        errors.append(f"SQL :{','.join(sorted(missing_in_config))} not in config params")
    if extra_in_config:
        errors.append(f"Config params {sorted(extra_in_config)} not used in SQL")
    if bad_types:
        errors.append(
            "Invalid types: " + ", ".join(f"{n}={t!r}" for n, t in bad_types)
        )
    return (not errors, "; ".join(errors))
```

Note: `read_columns.params.filter` and `read_columns.params.max_rows` from `default_queries.toml` are NOT in the SQL — they're filter/format helpers. The verify check should accept the standard names `filter` and `max_rows` as legitimate "extra" config params (or skip the "extra in config" check entirely for cleanliness). Choose: **only flag truly unused params** by allow-listing `{"filter", "max_rows"}` as legitimate config-only params.

---

## HOW — `verify_queries`

```python
def verify_queries(queries, backend_name, backend):
    result = {}
    for name, qcfg in queries.items():
        sql = qcfg.resolve_sql(backend_name)

        ok, err = _check_sql_explain(sql, qcfg.params, backend_name, backend)
        result[f"{name}.sql"] = {"ok": ok, "value": "EXPLAIN ok" if ok else "failed",
                                 "error": err, "install_hint": ""}

        ok, err = _check_params_well_formed(sql, qcfg.params)
        result[f"{name}.params"] = {"ok": ok, "value": "well-formed" if ok else "issue",
                                    "error": err, "install_hint": ""}

        ok = qcfg.max_rows > 0
        result[f"{name}.max_rows"] = {
            "ok": ok,
            "value": str(qcfg.max_rows),
            "error": "" if ok else "max_rows must be > 0",
            "install_hint": "",
        }
    result["overall_ok"] = all(e["ok"] for k, e in result.items() if k != "overall_ok")
    return result
```

---

## Orchestrator wiring

In step 7, the orchestrator already had a placeholder `if connection_ok: sections += QUERIES`. Replace the TODO with the real call:

```python
sections.append(("QUERIES", verify_queries(query_config.queries, backend_name, backend)))
```

`backend` here is the **already-open** backend returned as the second element of `verify_connection`'s 2-tuple (which has been the contract since step 7). The `try/finally` that closes the backend after the M2 sections run was wired into the orchestrator in **step 7** (where the open-backend path first appears); step 8 inherits that lifecycle and just plugs in the QUERIES section.

---

## ALGORITHM — orchestrator (M2 partial)

```
... M1 sections ...
if connection ok:
    # backend is already connected (returned from verify_connection in step 7);
    # the surrounding try/finally that closes it lives in step 7's orchestrator.
    sections += QUERIES(queries, backend_name, backend)
    sections += UPDATES(...)         # step 9
```

The decision to have `verify_connection` return `(result_dict, open_backend_or_None)` and the try/finally that closes the backend both already landed in step 7. Step 8 only fills in the QUERIES section.

---

## DATA — Allow-listed config-only param names

```python
_LEGITIMATE_NON_SQL_PARAMS = {"filter", "max_rows"}
```

---

## Tests — extend `tests/cli/test_verify.py`

| Test | Asserts |
|---|---|
| `test_verify_queries_valid_sqlite` | A query with valid SQL + matching params + max_rows>0 → all `ok=True` |
| `test_verify_queries_detects_invalid_sql` | Issue test (xii): `SELECT * FROMX badtable` → `<name>.sql` row ok=False with sqlite error |
| `test_verify_queries_detects_param_mismatch` | Issue test (xiii): SQL has `:foo` but config has `:bar` → `<name>.params` row ok=False |
| `test_verify_queries_detects_invalid_param_type` | Param type `"bool"` (not in allowed set) → ok=False |
| `test_verify_queries_accepts_filter_and_max_rows_as_non_sql_params` | A query with `filter` and `max_rows` config params but neither in SQL → ok=True |
| `test_verify_queries_detects_missing_max_rows` | `QueryConfig(max_rows=0)` → ok=False |
| `test_verify_queries_unimplemented_backend_explain_fails_cleanly` | mssql backend's `explain()` raises NotImplementedError → ok=False with clear error string |

Use the `sqlite_db` fixture from `conftest.py` to get a real SQLite db for EXPLAIN tests.

---

## Quality gates

All five checks green.

---

## LLM Prompt for this step

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_8.md`. First, widen the `explain` signature on both `DatabaseBackend` (ABC) in `src/mcp_tools_sql/backends/base.py` and `SQLiteBackend` in `src/mcp_tools_sql/backends/sqlite.py` to `explain(self, sql: str, params: dict[str, Any] | None = None) -> str`; for SQLite, bind `params or {}` to the cursor (backwards-compatible — existing callers still pass only `sql`). Then implement `verify_queries(queries, backend_name, backend)` in `src/mcp_tools_sql/cli/commands/verify.py`. For each query, emit three rows: `<name>.sql` (for SQLite, build a dummy params dict per declared type and call `backend.explain(sql, dummy)`; otherwise call `backend.explain(sql)` — failures become `[ERR]` with the exception text; this also covers the "unimplemented backend" case automatically), `<name>.params` (`:name` in SQL ↔ config params with allow-list `{"filter", "max_rows"}` as legitimate config-only params; each `type` must be in `{"str","int","float","datetime"}`), `<name>.max_rows` (must be > 0). Wire into the orchestrator after `verify_connection` succeeds; the open-backend lifecycle (return-tuple + try/finally) is already in place from step 7. Add the listed tests covering issue tests (xii) and (xiii). Run all quality checks and ensure they pass.
