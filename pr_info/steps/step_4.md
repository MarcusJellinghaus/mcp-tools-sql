# Step 4 — Per-entry verify extraction + CLI snapshot regression

**Prompt for LLM:**
> Read `pr_info/steps/summary.md` and then implement `pr_info/steps/step_4.md`.
> Steps 1-3 are merged. Work sequence within the single commit:
> (i) add the CLI stdout snapshot test as a regression guard — it must pass
>     against the **current** `verify.py` before any refactor — and capture
>     the snapshot fixture;
> (ii) extract `verify_one_query` / `verify_one_update` and rewire the bulk
>     functions to aggregate;
> (iii) add the per-entry equality tests (they import the freshly extracted
>     functions, so they cannot exist before step ii);
> (iv) re-run the snapshot test and confirm byte-identity vs. step i.
> All four pieces ship in a single commit. Run all gates at the end.

---

## WHERE

- **Modify (impl):** `src/mcp_tools_sql/cli/commands/verify.py`.
- **Modify (tests):** `tests/cli/test_verify.py` — append per-entry tests +
  snapshot test.
- **New file (fixture in):** `tests/cli/fixtures/verify_snapshot.toml` — a
  query config that exercises the happy / missing-table / bad-identifier
  branches for queries and updates against a fixed sqlite schema.
- **New file (fixture out):** `tests/cli/fixtures/verify_snapshot.txt` —
  byte-snapshot of the `=== QUERIES ===` + `=== UPDATES ===` slices from
  running `verify` against the above config.

## WHAT

Two new public functions in `verify.py`:

```python
def verify_one_query(
    name: str,
    qcfg: QueryConfig,
    backend_name: str,
    backend: DatabaseBackend,
) -> dict[str, Any]: ...

def verify_one_update(
    name: str,
    ucfg: UpdateConfig,
    backend_name: str,
    backend: DatabaseBackend,
) -> dict[str, Any]: ...
```

- Both return a dict with **exactly the per-entry keys that the bulk function
  emits today, in the same order**.
- No `overall_ok` key.
- `verify_one_query` always returns 3 rows
  (`<n>.sql`, `<n>.params`, `<n>.max_rows_default`).
- `verify_one_update` returns 1 row (`<n>.table`) on the bad-identifier path,
  3 rows (`<n>.table`, `<n>.key_column`, `<n>.fields`) on the missing-table
  and happy paths.

## HOW

- Imports: already present in `verify.py`. No new imports needed.
- The existing bulk loops are replaced by:

```python
def verify_queries(queries, backend_name, backend):
    result: dict[str, Any] = {}
    for name, qcfg in queries.items():
        result.update(verify_one_query(name, qcfg, backend_name, backend))
    result["overall_ok"] = all(
        entry["ok"] for key, entry in result.items() if key != "overall_ok"
    )
    return result
```
and the analogous wrapper for `verify_updates`.

- Inside `verify_one_query` / `verify_one_update`, **lift the current loop
  body verbatim** — no comprehensions, no `dict(...)` constructors, no key
  reordering. Add a single inline comment near each early-return branch in
  `verify_one_update`:

```python
# NOTE: Key insertion order is load-bearing — the CLI snapshot test and
# verify_queries/verify_updates assert byte-equality against this order.
# Do not refactor to dict comprehensions or dict() constructors.
```

## ALGORITHM

`verify_one_query`:
```
result: dict[str, Any] = {}
sql = qcfg.resolve_sql(backend_name)
ok, err = _check_sql_explain(sql, qcfg.params, backend_name, backend)
result[f"{name}.sql"] = _entry(ok=ok, value=("EXPLAIN ok" if ok else "failed"), error=err)
ok, err = _check_params_well_formed(sql, qcfg.params)
result[f"{name}.params"] = _entry(ok=ok, value=("well-formed" if ok else "issue"), error=err)
ok = qcfg.max_rows_default > 0
result[f"{name}.max_rows_default"] = _entry(ok=ok, value=str(qcfg.max_rows_default),
                                            error=("" if ok else "max_rows_default must be > 0"))
return result
```

`verify_one_update`: copy the current per-iteration body verbatim. The
current `verify_updates` loop body has TWO `continue` statements that must
BOTH be rewritten as `return result`:

1. **Bad-identifier branch** — when the table name (or schema/key/field
   identifier) fails validation. After populating
   `result[f"{name}.table"]` with the `[ERR]` entry, the bulk loop hits
   `continue`. In the extracted function, replace with `return result`
   (so the function returns a single-row dict — 1 row).
2. **Missing-table branch** — when the table does not exist in the live
   schema. After populating `result[f"{name}.table"]`,
   `result[f"{name}.key_column"]`, and `result[f"{name}.fields"]` each
   with `[ERR]` entries, the bulk loop hits `continue`. In the extracted
   function, replace with `return result` (3-row dict).
3. **Happy path** — falls through to populate all three rows
   (`{name}.table`, `{name}.key_column`, `{name}.fields`) and reaches the
   final `return result` (3-row dict).

All `result[...] = ...` lines remain untouched; only the two `continue`
statements become `return result`.

## DATA

Both functions return `dict[str, dict[str, Any]]` where each inner dict has
the `_entry` shape (`ok`, `value`, `error`, `install_hint`). No `overall_ok`.

## Tests

### Fixture `tests/cli/fixtures/verify_snapshot.toml`

Contains a connection pointing at a sqlite db prepared by the test
(`schema` with `users(id INTEGER, email TEXT)` and `customers(id INTEGER,
name TEXT, country TEXT)`), three queries and three updates exercising:

- Query: happy path (`get_user` against `users`).
- Query: invalid SQL (`bad_sql` with malformed SQL).
- Query: param mismatch (`mismatched_params`).
- Update: happy path (`set_user_email` on `users`).
- Update: missing-table (`set_missing` on non-existent table).
- Update: bad-identifier (`bad_table` with `table = "drop;"`).

The corresponding `~/.mcp-tools-sql/config.toml` is generated in the test's
`tmp_path` (mirroring the pattern used elsewhere in `test_verify.py`).

### Snapshot test

```python
def test_verify_cli_queries_updates_snapshot(tmp_path, capsys) -> None:
    # Prepare sqlite db schema, fixture configs in tmp_path.
    # Invoke verify_cmd.run(...).
    captured = capsys.readouterr().out
    queries_block = _extract_section(captured, "QUERIES")
    updates_block = _extract_section(captured, "UPDATES")
    actual = f"=== QUERIES ===\n{queries_block}\n=== UPDATES ===\n{updates_block}\n"
    expected = (Path(__file__).parent / "fixtures" / "verify_snapshot.txt").read_text(encoding="utf-8")
    assert actual == expected
```

`_extract_section` is a small private helper inside the test module: split
stdout on `"=== "` headers and return the body up to the next blank
separator.

**Config wiring:** the snapshot test invokes `verify_cmd.run` with an
explicit `--database-config` (or equivalent argv) pointing at a fixture
config written into `tmp_path`, so the test never picks up the user's real
`~/.mcp-tools-sql/config.toml`.

The snapshot is captured **before** the refactor, committed, and must remain
byte-identical after the refactor.

### Per-entry equality tests

For each existing branch already covered in `test_verify.py`, add:

```python
def test_verify_one_query_matches_bulk_happy_path(sqlite_db):
    queries = {"foo": QueryConfig(sql="SELECT 1")}
    backend = SQLiteBackend(ConnectionConfig(backend="sqlite", path=str(sqlite_db)))
    backend.connect()
    try:
        bulk = verify_cmd.verify_queries(queries, "sqlite", backend)
        one = verify_cmd.verify_one_query("foo", queries["foo"], "sqlite", backend)
    finally:
        backend.close()
    bulk_without_overall = {k: v for k, v in bulk.items() if k != "overall_ok"}
    assert list(one.keys()) == list(bulk_without_overall.keys())   # order match
    assert one == bulk_without_overall                              # content match
```

Parametrize across:
- queries: happy path (1 case is enough — all queries take same 3-row path).
- updates: happy / missing-table / bad-identifier (3 cases — different row counts).

## Refactor safety checklist

- Run full `pytest -x` BEFORE the refactor to capture the snapshot.
- Run full `pytest -x` AFTER the refactor: snapshot must still be
  byte-equal, all 30+ existing verify tests must still pass.
- `pylint`, `mypy`, `ruff`, `tach check`, `lint-imports` clean.
