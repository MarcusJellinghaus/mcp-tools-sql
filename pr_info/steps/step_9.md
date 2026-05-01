# Step 9 — `verify` M2: UPDATES section

**Reference**: [summary.md](./summary.md) — section "`verify` M1 / M2 sections"
**Commit**: 9 of 10
**Goal**: Per-update validation: table exists, key column exists, field columns exist.

> **Note**: documentation work (existing-doc fixes + new `docs/cli.md`) lands in step 10. This step keeps the **final compliance check** section as a visible reminder mapping issue tests (i)–(xiv) to test files.

---

## WHERE

Modify:
- `src/mcp_tools_sql/cli/commands/verify.py`
- `tests/cli/test_verify.py` — extend

---

## WHAT — Function signatures

```python
def verify_updates(
    updates: dict[str, UpdateConfig],
    backend_name: str,
    backend: DatabaseBackend,
) -> dict[str, Any]:
    """
    For each update <name>, emit three rows:
      <name>.table:        table exists in schema
      <name>.key_column:   update.key.field exists in table
      <name>.fields:       all update.fields[*].field exist in table
    """


def _list_table_columns(
    backend: DatabaseBackend,
    backend_name: str,
    schema: str,
    table: str,
) -> list[str] | None:
    """
    Returns column names list, or None if the table doesn't exist.
    sqlite     → SELECT * FROM pragma_table_info(:table)
    mssql/pg   → SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA=:s AND TABLE_NAME=:t
    """
```

---

## HOW — `_list_table_columns` per backend

```python
def _list_table_columns(backend, backend_name, schema, table):
    if backend_name == "sqlite":
        rows = backend.execute_query(
            "SELECT name FROM pragma_table_info(:table)",
            {"table": table},
        )
        cols = [r["name"] for r in rows]
        return cols if cols else None

    if backend_name in ("mssql", "postgresql"):
        rows = backend.execute_query(
            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA = :schema AND TABLE_NAME = :table",
            {"schema": schema, "table": table},
        )
        cols = [r["COLUMN_NAME"] for r in rows]
        return cols if cols else None

    return None  # unknown backend
```

For SQLite, schema is ignored (single-database file).

For MSSQL/PG, `_list_table_columns` does **not** fall back to `dbo` / `public` automatically. Users must set `schema = "..."` in their `[updates.<name>]` config block when the table lives outside the connection's default schema. If `schema` is empty, the column lookup will simply fail to find the table and verify will report `<name>.table` as `[ERR] Table not found` — that is the **intended behavior**: verify reflects what the user configured, it does not silently substitute defaults that may differ between environments.

---

## HOW — `verify_updates`

```python
def verify_updates(updates, backend_name, backend):
    result: dict[str, Any] = {}
    for name, ucfg in updates.items():
        cols = _list_table_columns(backend, backend_name, ucfg.schema_name, ucfg.table)

        if cols is None:
            result[f"{name}.table"] = {
                "ok": False,
                "value": f"{ucfg.schema_name}.{ucfg.table}".lstrip("."),
                "error": "Table not found",
                "install_hint": "",
            }
            # If table missing, key + fields rows still emitted as [ERR] for clarity
            result[f"{name}.key_column"] = {"ok": False, "value": "(skipped)",
                                            "error": "Table not found", "install_hint": ""}
            result[f"{name}.fields"] = {"ok": False, "value": "(skipped)",
                                        "error": "Table not found", "install_hint": ""}
            continue

        result[f"{name}.table"] = {"ok": True, "value": ucfg.table, ...}

        # key column
        key_field = ucfg.key.field if ucfg.key else ""
        if not key_field:
            result[f"{name}.key_column"] = {"ok": False, "value": "(none)",
                                            "error": "No key configured", "install_hint": ""}
        elif key_field not in cols:
            result[f"{name}.key_column"] = {"ok": False, "value": key_field,
                                            "error": f"Column not found in {ucfg.table}",
                                            "install_hint": ""}
        else:
            result[f"{name}.key_column"] = {"ok": True, "value": key_field, ...}

        # field columns
        missing = [f.field for f in ucfg.fields if f.field not in cols]
        if missing:
            result[f"{name}.fields"] = {
                "ok": False,
                "value": ", ".join(f.field for f in ucfg.fields),
                "error": f"Missing columns: {', '.join(missing)}",
                "install_hint": "",
            }
        else:
            result[f"{name}.fields"] = {
                "ok": True,
                "value": f"{len(ucfg.fields)} columns",
                "error": "", "install_hint": "",
            }

    result["overall_ok"] = all(e["ok"] for k, e in result.items() if k != "overall_ok")
    return result
```

---

## Orchestrator wiring

Replace the `# step 9` placeholder added in step 8:

```python
sections.append(("UPDATES", verify_updates(query_config.updates, backend_name, backend)))
```

The orchestrator now is fully wired:

```
ENVIRONMENT → CONFIG (with WARN) → DEPENDENCIES → BUILTIN
  → CONNECTION
    if ok:
      → QUERIES
      → UPDATES
    else:
      → render_skip_m2_summary
  → INSTALL INSTRUCTIONS (if any hints collected)
  → summary line
  → exit code
```

---

## ALGORITHM — `verify_updates`

```
for each update name, cfg:
    cols = _list_table_columns(backend, backend_name, cfg.schema_name, cfg.table)
    if cols is None: emit table=ERR, key=ERR, fields=ERR
    else:
        emit table=OK
        check key.field in cols → OK or ERR
        check all fields[*].field in cols → OK or ERR with missing list
return result
```

---

## DATA

All entries: standard dict shape `{"ok", "value", "error", "install_hint"}`.

---

## Tests — extend `tests/cli/test_verify.py`

| Test | Asserts |
|---|---|
| `test_verify_updates_valid_sqlite` | An update on the `customers` table from `sqlite_db` fixture with key=`id` and fields=`name,country` → all rows ok |
| `test_verify_updates_detects_missing_table` | Update on table `does_not_exist` → all three rows ok=False |
| `test_verify_updates_detects_missing_key_column` | Key column `nonexistent_id` → key row ok=False, table row ok=True |
| `test_verify_updates_detects_missing_field_column` | Issue test (xiv): one of the fields is `nonexistent_field` → fields row ok=False with missing column listed |
| `test_verify_updates_no_updates_configured` | Empty updates dict → empty result, overall_ok=True |
| `test_verify_full_run_with_queries_and_updates_returns_0` | Issue tests (vii)+(viii)+(x): full sqlite happy path → exit 0 |

---

## Quality gates

All five checks green.

**Final compliance check**: confirm all 14 issue test cases (i)–(xiv) are covered across the test files:
- (i)–(vi): `tests/cli/test_init.py` (step 4)
- (vii)–(xi): `tests/cli/test_verify.py` (steps 5–7)
- (xii)–(xiii): `tests/cli/test_verify.py` (step 8)
- (xiv): `tests/cli/test_verify.py` (step 9)

---

## LLM Prompt for this step

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_9.md`. Implement `verify_updates(updates, backend_name, backend)` in `src/mcp_tools_sql/cli/commands/verify.py`. For each update, emit three rows: `<name>.table` (resolved via the small helper `_list_table_columns` — SQLite uses `pragma_table_info(:table)`; MSSQL/PostgreSQL use `INFORMATION_SCHEMA.COLUMNS` filtered by `TABLE_SCHEMA` + `TABLE_NAME`), `<name>.key_column` (the configured key field exists in the table), `<name>.fields` (all configured fields exist; report missing columns explicitly). When the table is not found, emit all three rows as `[ERR]` rather than skipping. Wire into the orchestrator (replace the step-8 placeholder). Add the listed tests covering issue test (xiv) and the full happy-path. Run all quality checks and confirm they pass. As a final check, verify that all 14 issue test cases (i)–(xiv) are present across the test files.
