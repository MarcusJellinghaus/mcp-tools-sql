# Step 12 — verify: static CONFIG cross-file checks

See `pr_info/steps/summary.md` → "verify" (decision 9, static rules). No DB access.

## WHERE
- `src/mcp_tools_sql/verification/config_files.py`
- Tests: `tests/verification/test_config_files.py`, `tests/cli/test_verify.py`
  (snapshot fixture may need regeneration)

## WHAT
Extend `verify_config_files` with static cross-file rows (added after the existing
parse rows, before `overall_ok`), each `make_entry(ok=..., value=..., error=...)`:
1. query file `connection` names a real entry in `connections`
2. each connection's `default_database` ∈ its `databases`
3. `databases` non-empty; exactly one for postgresql; `["main"]` for sqlite
4. each `[queries.*].connection`, if set, names a real connection
5. each `[queries.*].database`, if set, ∈ that connection's `databases`
6. same for `[updates.*]`
7. legacy `database` not conflicting with explicit `databases`

## HOW
Load both configs (already available via `load_query_config` /
`load_database_config`). Rules 2/3/7 are largely enforced by the Step 3 model
validators — surface those as PASS rows here (and as an `[ERR]` row if model
validation raised). Rules 1/4/5/6 are cross-file and checked here explicitly.
Keep insertion order stable (verify snapshot asserts byte-equality).

## ALGORITHM
```
load qcfg, dbcfg (guarded)
row("connection_valid", qcfg.connection in dbcfg.connections)
for scope in (queries, updates):
    for name, cfg in scope:
        if cfg.connection: row(f"{scope}.{name}.connection", cfg.connection in conns)
        if cfg.database:   row(..., cfg.database in conns[resolved].databases)
recompute overall_ok
```

## DATA
Standard verifier result dict; new rows keyed descriptively; `overall_ok`
recomputed to include them.

## TESTS (write first)
- Valid multi-connection config → all new rows PASS.
- Unknown file `connection` → its row `[ERR]` (fixes the "section vanishes"
  bug — decision 9 side effect).
- `[queries.x].database` not in the connection's databases → `[ERR]`.
- `[queries.x].connection` unknown → `[ERR]`.
- Single-target legacy config → new rows PASS, no behaviour change.
- Regenerate/adjust `tests/cli/fixtures/verify_snapshot.txt` if ordering changes.

## LLM PROMPT
> Implement Step 12 from `pr_info/steps/step_12.md` (context in
> `pr_info/steps/summary.md`). Add static cross-file checks (rules 1–7) to
> `verification/config_files.py` as ordered result rows with no database access,
> recomputing `overall_ok`. Write tests first (valid multi config passes; unknown
> connection, bad per-query database/connection each `[ERR]`; single-target legacy
> unchanged) and update the verify snapshot fixture if ordering shifts. Run pylint,
> pytest (`-n auto` + unit markers), mypy, lint-imports/tach; all green. One commit.
