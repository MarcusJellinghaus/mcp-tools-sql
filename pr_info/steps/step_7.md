# Step 7 — `verify`: CONNECTION + INSTALL INSTRUCTIONS + skip-M2-on-failure

**Reference**: [summary.md](./summary.md) — section "`verify` M1 / M2 sections"
**Commit**: 7 of 9
**Goal**: Complete M1 by adding CONNECTION verification, the aggregated INSTALL INSTRUCTIONS section, and the skip-M2-on-failure summary stub. Promote sensitive-key warning from step 5 into a real `[WARN]` row.

---

## WHERE

Modify:
- `src/mcp_tools_sql/cli/commands/verify.py`
- `tests/cli/test_verify.py` — extend

---

## WHAT — Function signatures

```python
def verify_connection(connection: ConnectionConfig) -> dict[str, Any]:
    """
    Build backend via create_backend(connection); on failure → [ERR].
    On success: connect, run SELECT 1, close.
    Reports rows for: backend, driver (mssql only), host_or_path, database, credentials_resolved, select_1.
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

# Actually try to connect and SELECT 1
try:
    backend = create_backend(connection)
    with backend:
        backend.execute_query("SELECT 1")
    result["select_1"] = {"ok": True, "value": "ok", ...}
except Exception as exc:
    result["select_1"] = {"ok": False, "value": "failed",
                          "error": str(exc), "install_hint": ""}

result["overall_ok"] = all(e["ok"] for k, e in result.items() if k != "overall_ok")
return result
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

## HOW — Skip-M2-on-failure summary

Add a placeholder in the orchestrator. M2 sections are added in steps 8–9, but the wiring lands here:

```python
connection_ok = connection_section_result.get("overall_ok", False)

if connection_ok:
    sections.append(("QUERIES", verify_queries(...)))   # added in step 8
    sections.append(("UPDATES", verify_updates(...)))   # added in step 9
else:
    n_queries = len(query_config.queries)
    n_updates = len(query_config.updates)
    print(render_skip_m2_summary(n_queries, n_updates))
```

For step 7, `verify_queries` / `verify_updates` are not yet implemented; just leave a TODO comment for steps 8/9 to plug in. The skip-summary path can already be tested.

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
    sections += CONNECTION
    if connection ok:
        sections += QUERIES (TODO step 8)
        sections += UPDATES (TODO step 9)
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

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_7.md`. Extend `src/mcp_tools_sql/cli/commands/verify.py` with: (1) `verify_connection(connection)` that reports backend, driver (mssql only), host:port or sqlite path, database, credentials resolution, and a `SELECT 1` round-trip via `create_backend()`; (2) `collect_install_instructions(sections)` that dedupes `install_hint` strings from failed entries; (3) `render_skip_m2_summary(n_queries, n_updates)` returning the issue's exact summary string; (4) promote sensitive-key detection in `verify_config_files` from a deferred row to a real `[WARN]` row using a `warn=True` flag on the entry dict; update the formatter and the summary counters to recognize the warn path (warn does NOT raise the exit code). Wire all of these into `run(args)` so the M1 orchestrator is complete; QUERIES / UPDATES are still placeholders for steps 8/9 but the skip-on-failure branch should already be exercised. Add the listed tests covering issue tests (vii), (xi), plus connection variants. Run all quality checks and ensure they pass.
