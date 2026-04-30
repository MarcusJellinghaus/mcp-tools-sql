# Step 8 — `verify` M2: QUERIES section

**Reference**: [summary.md](./summary.md) — section "`verify` M1 / M2 sections"
**Commit**: 8 of 9
**Goal**: Per-query validation: SQL valid via EXPLAIN, params well-formed, max_rows set.

---

## WHERE

Modify:
- `src/mcp_tools_sql/cli/commands/verify.py`
- `tests/cli/test_verify.py` — extend

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


def _check_sql_explain(sql: str, backend_name: str, backend: DatabaseBackend) -> tuple[bool, str]:
    """Return (ok, error_message)."""


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
def _check_sql_explain(sql, backend) -> tuple[bool, str]:
    try:
        backend.explain(sql)
        return True, ""
    except Exception as exc:
        return False, str(exc)
```

---

## HOW — `_check_params_well_formed`

Re-use the existing `_extract_sql_params` regex (currently in `schema_tools.py`). Either:
- Import it (ok per layered architecture: cli → schema_tools is allowed via tach config from step 3), OR
- Duplicate the small regex (3 lines).

Pick **import** to avoid duplication.

```python
from mcp_tools_sql.schema_tools import _extract_sql_params

def _check_params_well_formed(sql, params):
    sql_names = _extract_sql_params(sql)
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

        ok, err = _check_sql_explain(sql, backend)
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

(`backend` here is the live, connected backend instance from `verify_connection`. To avoid double-connection, restructure step 7's connection check to keep the backend open and pass it to step 8/9. Wrap in a `try/finally` to ensure close.)

---

## ALGORITHM — orchestrator (M2 partial)

```
... M1 sections ...
if connection ok:
    open backend (already connected from verify_connection)
    sections += QUERIES(queries, backend_name, backend)
    sections += UPDATES(...)         # step 9
    close backend
```

Restructuring step 7's `verify_connection` to either (a) return the open backend, or (b) connect twice (once for SELECT 1, again for EXPLAINs) is a small choice. Prefer (a): change `verify_connection`'s contract to return `(result_dict, open_backend_or_None)`. Caller closes.

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

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_8.md`. Implement `verify_queries(queries, backend_name, backend)` in `src/mcp_tools_sql/cli/commands/verify.py`. For each query, emit three rows: `<name>.sql` (calls `backend.explain(sql)` — failures become `[ERR]` with the exception text; this also covers the "unimplemented backend" case automatically), `<name>.params` (`:name` in SQL ↔ config params with allow-list `{"filter", "max_rows"}` as legitimate config-only params; each `type` must be in `{"str","int","float","datetime"}`), `<name>.max_rows` (must be > 0). Wire into the orchestrator after `verify_connection` succeeds; restructure `verify_connection` to return `(result_dict, open_backend_or_None)` so the live backend can be reused for EXPLAINs without reconnecting. Caller closes the backend in a `try/finally`. Add the listed tests covering issue tests (xii) and (xiii). Run all quality checks and ensure they pass.
