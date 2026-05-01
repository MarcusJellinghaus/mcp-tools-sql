# Step 6 — `verify`: DEPENDENCIES + BUILTIN sections

**Reference**: [summary.md](./summary.md) — section "`verify` M1 / M2 sections"
**Commit**: 6 of 10
**Goal**: Add backend-conditional optional-dependency check and builtin tools count.

> **Decision — `tools_registered_count` semantic (Round 2 update)**: keep scope minimal. `tools_registered_count = len(load_default_queries())` — the total entries in `default_queries.toml`. **No** helper extracted from `server.py`, **no** filtering on disabled queries or per-backend overrides in this PR. Real filtering (when disabled / per-backend filtering actually exists in `server.py`) is deferred to a follow-up PR; until then, `verify_builtin` and `server.py` mount logic don't need to share a helper because there's nothing to filter. See Decisions.md Round 2 / Q1.

---

## WHERE

Modify:
- `src/mcp_tools_sql/cli/commands/verify.py`
- `tests/cli/test_verify.py` — extend

---

## WHAT — Function signatures

```python
def verify_dependencies(backend: str) -> dict[str, Any]:
    """
    Backend-conditional check of optional/extra deps.
    sqlite     → single info entry: "(no optional dependencies for sqlite)"
    mssql      → import pyodbc + check pyodbc.drivers() for "SQL Server" substring
    postgresql → import psycopg
    """


def verify_builtin() -> dict[str, Any]:
    """
    Loads default_queries.toml; reports:
      default_queries_loaded: ok if dict non-empty
      tools_registered_count: len(load_default_queries()) — always ok=True
    """
```

The orchestrator now needs to know which backend is requested for the DEPENDENCIES section. Read it from the resolved query config (`query_config.connection` → look up in db config → `connection.backend`). If config-loading failed in the previous section, `verify_dependencies` is called with the backend `"unknown"` → emits a single `[ERR]` row "cannot determine backend without valid config" and the rest of the section is skipped. `verify_builtin` does **not** need the backend name — it just counts entries in `default_queries.toml`.

---

## HOW — `verify_dependencies` per branch

### sqlite
```python
return {
    "info": {"ok": True, "value": "(no optional dependencies for sqlite)",
             "error": "", "install_hint": ""},
    "overall_ok": True,
}
```

### mssql
```python
result: dict[str, Any] = {}
try:
    import pyodbc
    result["pyodbc"] = {"ok": True, "value": pyodbc.version, ...}
except ImportError as exc:
    result["pyodbc"] = {"ok": False, "value": "(not installed)", "error": str(exc),
                        "install_hint": "pip install mcp-tools-sql[mssql]"}

try:
    drivers = pyodbc.drivers() if "pyodbc" in sys.modules else []
    has_sql_server = any("SQL Server" in d for d in drivers)
    result["odbc_driver"] = {
        "ok": has_sql_server,
        "value": next((d for d in drivers if "SQL Server" in d), "(none found)"),
        "error": "" if has_sql_server else "No ODBC driver containing 'SQL Server' found",
        "install_hint": "" if has_sql_server else
            "Install Microsoft ODBC Driver 18 for SQL Server "
            "(https://learn.microsoft.com/sql/connect/odbc/download-odbc-driver-for-sql-server)",
    }
except Exception:
    result["odbc_driver"] = {"ok": False, ...}
```

### postgresql
```python
try:
    import psycopg
    result["psycopg"] = {"ok": True, "value": psycopg.__version__, ...}
except ImportError as exc:
    result["psycopg"] = {"ok": False, "value": "(not installed)", "error": str(exc),
                         "install_hint": "pip install mcp-tools-sql[postgresql]"}
```

---

## HOW — `verify_builtin`

```python
from mcp_tools_sql.schema_tools import load_default_queries

queries = load_default_queries()
tools_registered_count = len(queries)

return {
    "default_queries_loaded": {"ok": bool(queries),
                               "value": f"{len(queries)} queries", ...},
    "tools_registered_count": {"ok": True,
                               "value": f"{tools_registered_count} tools", ...},
    "overall_ok": bool(queries),
}
```

Minimal scope: `tools_registered_count = len(load_default_queries())`. No helper extracted from `server.py`, no per-backend or disabled-query filtering. When real filtering is introduced into `server.py` (follow-up PR), `verify_builtin` and the server mount path can be aligned then. See Decisions.md Round 2 / Q1.

---

## Orchestrator wiring

`run(args)` now needs the backend name. Resolve it once (after `verify_config_files` succeeds), pass to `verify_dependencies`. If config failed, pass `"unknown"`.

```python
backend = "unknown"
try:
    qcfg = load_query_config(<resolved path>)
    dbcfg = load_database_config(args.database_config)
    conn = resolve_connection(qcfg, dbcfg)
    backend = conn.backend
except Exception as exc:
    logger.debug("Could not resolve backend: %s", exc)

sections.append(("DEPENDENCIES", verify_dependencies(backend)))
sections.append(("BUILTIN", verify_builtin()))
```

---

## ALGORITHM — orchestrator

```
sections = [ENVIRONMENT, CONFIG]
backend = resolve backend from configs (or "unknown")
sections += DEPENDENCIES(backend)
sections += BUILTIN
print + summarize
```

---

## DATA — Return shape

Same as step 5:
```python
{"<key>": {"ok": bool, "value": str, "error": str, "install_hint": str}, "overall_ok": bool}
```

---

## Tests — extend `tests/cli/test_verify.py`

| Test | Asserts |
|---|---|
| `test_verify_dependencies_sqlite_shows_info_line` | sqlite branch returns `{"info": ...}` with the expected message |
| `test_verify_dependencies_unknown_backend_returns_err` | backend `"unknown"` → ok=False |
| `test_verify_run_uses_unknown_backend_when_config_invalid` | Pass an invalid (or absent) query/db config so config-loading raises in the orchestrator; assert `DEPENDENCIES` section is rendered with `backend == "unknown"` (e.g. its single `[ERR]` row "cannot determine backend without valid config" is present in the output, and `verify_builtin` still runs) |
| `test_verify_dependencies_postgresql_when_psycopg_missing` | monkeypatch `sys.modules["psycopg"]` to raise on import → ok=False, install_hint set |
| `test_verify_builtin_returns_query_count` | Result has key with non-zero count |
| `test_verify_run_includes_dependencies_and_builtin_sections` | capsys: stdout contains `=== DEPENDENCIES ===` and `=== BUILTIN ===` |
| `test_verify_sqlite_full_run_all_ok` | Issue test (viii): valid SQLite config (with a real tmp sqlite db file referenced by db config) → all rows are `[OK]`, dependencies section shows the "no optional dependencies for sqlite" line. (Connection section will be added in step 7 — for now this test only checks env + config + deps + builtin.) |
| `test_verify_detects_missing_connection` | Issue test (ix): query config references a name not in db config → CONFIG/CONNECTION reports the mismatch. (Will need refinement in step 7 when CONNECTION section lands; in step 6, surface via the backend-resolution step in orchestrator.) |
| `test_verify_reports_default_queries_count` | Issue test (x): BUILTIN section shows "{N} queries" |

Skip tests that require the CONNECTION / QUERIES / UPDATES sections — they land in steps 7–9.

For the mssql tests we don't try to actually `import pyodbc` in CI (it may not be installed); use `unittest.mock.patch.dict(sys.modules, {"pyodbc": MagicMock(...)})` or simply test the function returns the correct shape regardless of import outcome.

---

## Quality gates

All five checks green.

---

## LLM Prompt for this step

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_6.md`. Extend `src/mcp_tools_sql/cli/commands/verify.py` with two new domain verifiers: `verify_dependencies(backend: str)` (sqlite shows a single "no optional dependencies for sqlite" info row; mssql checks `pyodbc` import and `pyodbc.drivers()` substring `"SQL Server"`; postgresql checks `psycopg` import; unknown backend returns a single `[ERR]` row) and `verify_builtin()` — no arguments — which reports `default_queries_loaded` and `tools_registered_count = len(load_default_queries())` (no helper extracted from `server.py`, no filtering on disabled / per-backend queries; that's deferred to a follow-up PR). Wire both into the `run(args)` orchestrator. The orchestrator should resolve the backend name from the config files (best-effort; on failure pass `"unknown"`) and pass it to `verify_dependencies` only. Add the listed tests to `tests/cli/test_verify.py` covering issue tests (viii), (ix) partial, and (x). Run all quality checks and ensure they pass.
