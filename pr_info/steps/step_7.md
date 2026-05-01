# Step 7 — `verify`: CONNECTION + INSTALL INSTRUCTIONS + skip-M2-on-failure

**Reference**: [summary.md](./summary.md) — section "`verify` M1 / M2 sections"
**Commit**: 7 of 10
**Goal**: Complete M1 by adding CONNECTION verification, the aggregated INSTALL INSTRUCTIONS section, and the skip-M2-on-failure summary stub. Promote sensitive-key warning from step 5 into a real `[WARN]` row.

> **Decision — `verify_connection` return shape**: `verify_connection` returns `(result_dict, open_backend_or_None)` from the **start** (this step). M1 callers ignore the second element. Step 8 then uses the open backend for EXPLAINs without reconnecting. This avoids restructuring `verify_connection`'s contract mid-stream.

---

## WHERE

Modify:
- `src/mcp_tools_sql/cli/commands/verify.py`
- `tests/cli/test_verify.py` — extend

---

## WHAT — Function signatures

```python
def verify_connection(
    connection: ConnectionConfig,
) -> tuple[dict[str, Any], DatabaseBackend | None]:
    """
    Build backend via create_backend(connection); on failure → [ERR] and return (result, None).
    On success: connect, run SELECT 1, leave the backend open and return it as the second tuple element.
    The caller is responsible for closing the open backend (try/finally in the orchestrator).
    Reports rows for: backend, driver (mssql only), host_or_path, database, credentials_resolved, select_1.

    Step 7 (M1) callers ignore the second element. Step 8/9 (M2) use it for EXPLAIN /
    INFORMATION_SCHEMA queries without reconnecting.
    """


def collect_install_instructions(
    sections: list[tuple[str, dict[str, Any]]],
) -> dict[str, Any]:
    """
    Aggregate install_hint from all failed entries across all sections.
    Returns one entry per unique install_hint string.
    overall_ok is always True (informational).
    """


def render_skip_m2_summary(query_count: int, update_count: int) -> str:
    """
    Returns: 'connection failed; skipped N query checks, M update checks'
    """
```

---

## HOW — `verify_connection`

```python
result: dict[str, Any] = {}
result["backend"] = {"ok": True, "value": connection.backend, ...}

if connection.backend == "mssql":
    result["driver"] = {"ok": bool(connection.driver),
                        "value": connection.driver or "(empty)", ...}

# host_or_path: for sqlite use path, otherwise host:port
if connection.backend == "sqlite":
    result["path"] = {"ok": bool(connection.path), "value": connection.path or "(empty)", ...}
else:
    host_value = f"{connection.host}:{connection.port}" if connection.host else "(empty)"
    result["host_port"] = {"ok": bool(connection.host), "value": host_value, ...}
    result["database"] = {"ok": bool(connection.database), "value": connection.database or "(empty)", ...}

# credentials_resolved
if connection.credential_env_var:
    val = os.environ.get(connection.credential_env_var)
    result["credentials"] = {
        "ok": val is not None,
        "value": f"env:{connection.credential_env_var}={'<set>' if val else '<missing>'}",
        "error": "" if val else f"Environment variable {connection.credential_env_var} not set",
        "install_hint": "",
    }
elif connection.password or connection.trusted_connection:
    result["credentials"] = {"ok": True, "value": "configured", ...}
else:
    result["credentials"] = {"ok": False, "value": "(none)",
                             "error": "No credentials configured", ...}

# Actually try to connect and SELECT 1.
# Leave backend OPEN on success (caller closes); on failure, return None.
open_backend: DatabaseBackend | None = None
try:
    backend = create_backend(connection)
    backend.connect()
    backend.execute_query("SELECT 1")
    result["select_1"] = {"ok": True, "value": "ok", ...}
    open_backend = backend
except Exception as exc:
    result["select_1"] = {"ok": False, "value": "failed",
                          "error": str(exc), "install_hint": ""}
    open_backend = None

result["overall_ok"] = all(e["ok"] for k, e in result.items() if k != "overall_ok")
return result, open_backend
```

---

## HOW — `collect_install_instructions`

```python
hints: list[str] = []
for _title, section in sections:
    for key, entry in section.items():
        if key == "overall_ok":
            continue
        hint = entry.get("install_hint", "")
        if hint and not entry["ok"]:
            hints.append(hint)

unique_hints = list(dict.fromkeys(hints))   # preserve order, dedupe
return {
    f"hint_{i}": {"ok": True, "value": h, "error": "", "install_hint": ""}
    for i, h in enumerate(unique_hints)
} | {"overall_ok": True}
```

If empty, the orchestrator should skip printing the section header (or print "(no install actions needed)") — pick "skip the section if empty" for KISS.

---

## HOW — Sensitive-key WARN row

In `verify_config_files` (from step 5), when sensitive keys are detected, emit:

```python
result["query_config_sensitive_keys"] = {
    "ok": False,           # treated as warning, not error
    "value": ", ".join(found),
    "error": "Move credentials to ~/.mcp-tools-sql/config.toml",
    "install_hint": "",
    "warn": True,          # NEW flag
}
```

Update the formatter to recognize `warn=True`:
```python
if entry.get("warn"):
    print(_format_row("warn", key, entry.get("value", ""), entry.get("error", "")))
    warn += 1
elif entry["ok"]:
    print(_format_row("ok", key, ...))
    ok += 1
else:
    print(_format_row("err", key, ...))
    err += 1
```

A `warn` does **not** set the exit code to 1 — only `err` does.

---

## HOW — Skip-M2-on-failure summary + open-backend lifecycle

Add the M2 wiring in the orchestrator. M2 sections are added in steps 8–9, but the **lifecycle** (open-backend `try/finally`) is set up here, since step 7 is where the open-backend path first appears. Steps 8 and 9 just plug their section calls in — they do not need to touch the lifecycle wiring.

```python
connection_section_result, open_backend = verify_connection(connection)
sections.append(("CONNECTION", connection_section_result))
connection_ok = connection_section_result.get("overall_ok", False)

if connection_ok:
    # open_backend is non-None on success; close it after M2 finishes (or any error in M2).
    try:
        sections.append(("QUERIES", verify_queries(...)))   # added in step 8
        sections.append(("UPDATES", verify_updates(...)))   # added in step 9
    finally:
        if open_backend is not None:
            open_backend.close()
else:
    # M2-skip branch — no open backend to close (open_backend is None on failure).
    n_queries = len(query_config.queries)
    n_updates = len(query_config.updates)
    print(render_skip_m2_summary(n_queries, n_updates))
```

For step 7, `verify_queries` / `verify_updates` are not yet implemented; leave a TODO comment for steps 8/9 to plug in. The `try/finally` block and the skip-summary path can both already be exercised by tests.

---

## ALGORITHM — orchestrator (M1 complete)

```
sections = []
sections += ENVIRONMENT
sections += CONFIG (with WARN for sensitive keys)
backend = resolve backend or "unknown"
sections += DEPENDENCIES(backend)
sections += BUILTIN
if connection resolved:
    sections += CONNECTION  # verify_connection returns (result, open_backend_or_None)
    if connection ok:
        try:
            sections += QUERIES (TODO step 8)
            sections += UPDATES (TODO step 9)
        finally:
            close open_backend if non-None
    else:
        print render_skip_m2_summary(...)
hints = collect_install_instructions(sections)
if hints has any entries:
    sections += INSTALL_INSTRUCTIONS
print all sections + summary
return exit code
```

---

## DATA — Exit code rules (final)

- 0 if `err == 0`
- 1 otherwise
- `warn` count is reported but does not affect exit code

---

## Tests — extend `tests/cli/test_verify.py`

| Test | Asserts |
|---|---|
| `test_verify_connection_sqlite_select_1_ok` | tmp file SQLite db → all rows `ok=True`, `select_1` value `"ok"` |
| `test_verify_connection_sqlite_missing_path` | `path=""` → ok=False with helpful error |
| `test_verify_connection_unimplemented_backend_is_err` | `backend="postgresql"` (no impl) → `select_1.ok=False` from create_backend ValueError |
| `test_verify_connection_credential_env_var_missing` | env var unset → credentials row ok=False |
| `test_verify_connection_credential_env_var_set` | env var set → credentials row ok=True |
| `test_verify_detects_missing_connection` | Issue test (ix): query config references a connection name that does **not** exist in the database config → orchestrator surfaces the mismatch as an `[ERR]` (either in CONFIG via `resolve_connection` or as a CONNECTION-section failure with a clear message). Exit code 1. |
| `test_verify_connection_returns_open_backend_on_success` | `verify_connection` returns a 2-tuple; second element is non-None and is a connected `DatabaseBackend` instance (caller responsible for closing) |
| `test_verify_connection_returns_none_backend_on_failure` | On `select_1` failure, second tuple element is `None` |
| `test_collect_install_instructions_aggregates_unique` | Failed entries with same hint dedupe |
| `test_verify_run_skips_m2_on_connection_failure` | Issue test (xi): unreachable backend → stdout contains `connection failed; skipped 0 query checks, 0 update checks` |
| `test_verify_warn_for_sensitive_keys_in_query_config` | Query config with `password = "..."` → `[WARN]` row, exit code still 0 (or 1 if other err) — exit code 1 only if a true error exists |
| `test_verify_full_sqlite_run_returns_0` | Issue test (vii)+(viii): valid sqlite config + connectable db → exit 0 |
| `test_verify_full_run_returns_1_on_error` | Issue test (vii): missing config → exit 1 |

---

## Quality gates

All five checks green.

---

## LLM Prompt for this step

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_7.md`. Extend `src/mcp_tools_sql/cli/commands/verify.py` with: (1) `verify_connection(connection)` returning `(result_dict, open_backend_or_None)` — reports backend, driver (mssql only), host:port or sqlite path, database, credentials resolution, and a `SELECT 1` round-trip via `create_backend()`; on success the backend is **left open** and returned as the second tuple element; on failure the second element is `None`; (2) `collect_install_instructions(sections)` that dedupes `install_hint` strings from failed entries; (3) `render_skip_m2_summary(n_queries, n_updates)` returning the issue's exact summary string; (4) promote sensitive-key detection in `verify_config_files` from a deferred row to a real `[WARN]` row using a `warn=True` flag on the entry dict; update the formatter and the summary counters to recognize the warn path (warn does NOT raise the exit code). Wire all of these into `run(args)` so the M1 orchestrator is complete, including the **open-backend `try/finally` lifecycle** that closes the backend after the M2 sections finish (QUERIES / UPDATES are placeholders for steps 8/9 but the surrounding `try/finally` and the skip-on-failure branch should already be in place and exercised by tests). Add the listed tests covering issue tests (vii), (xi), plus connection variants. Run all quality checks and ensure they pass.
