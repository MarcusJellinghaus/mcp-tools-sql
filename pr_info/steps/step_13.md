# Step 13 — verify: static CONFIG cross-file checks

See `pr_info/steps/summary.md` → "verify" (decision 9, static rules). No DB access.

## WHERE
- `src/mcp_tools_sql/verification/config_files.py`
- Tests: `tests/verification/test_config_files.py`, `tests/cli/test_verify.py`
  (snapshot fixture may need regeneration)

## WHAT
Extend `verify_config_files` with the **cross-file** static rows (added after the
existing parse rows, before `overall_ok`), each `make_entry(ok=..., value=...,
error=...)`:
1. query file `connection` names a real entry in `connections`
4. each `[queries.*].connection`, if set, names a real connection
5. each `[queries.*].database`, if set, ∈ that connection's `databases`
6. same for `[updates.*]`

Rules 2/3/7 from the issue (`default_database` ∈ `databases`; `databases`
non-empty / exactly-one-for-postgresql / `["main"]` for sqlite; legacy `database`
not conflicting with an explicit `databases`) are **fully enforced by the Step 3
model validators**, which raise `ValidationError` at load. A config that violates
any of them never loads, so verify can never reach a per-rule row with a
violation — those rules are therefore **not** emitted as their own checks here
(they have no reachable `[ERR]` path). They stay guaranteed by load; the only new
rows are the genuinely cross-file rules 1/4/5/6 that the model cannot see.

## HOW
Load both configs (already available via `load_query_config` /
`load_database_config`), **guarded**: if the load itself raises `ValidationError`
(i.e. a rule-2/3/7 violation, or any other model error), surface it through the
**existing** config-parse error row rather than as new per-rule rows — do not try
to reconstruct 2/3/7 as separate rows, because there is no config object to
inspect once load has failed. When load succeeds, rules 2/3/7 are already true, so
only the cross-file rules 1/4/5/6 are checked and appended here. Keep insertion
order stable (verify snapshot asserts byte-equality).

## ALGORITHM
```
load qcfg, dbcfg (guarded -> existing parse-error row on ValidationError, then stop)
row("connection_valid", qcfg.connection in dbcfg.connections)          # rule 1
for scope in (queries, updates):                                       # rules 4/5/6
    for name, cfg in scope:
        if cfg.connection: row(f"{scope}.{name}.connection", cfg.connection in conns)
        if cfg.database:   row(..., cfg.database in conns[resolved].databases)
recompute overall_ok
```

## DATA
Standard verifier result dict; new rows keyed descriptively; `overall_ok`
recomputed to include them.

## TESTS (write first)
- Valid multi-connection config → all new cross-file rows PASS.
- Unknown file `connection` → its row `[ERR]` (rule 1; fixes the "section
  vanishes" bug — decision 9 side effect).
- `[queries.x].database` not in the connection's databases → `[ERR]` (rule 5).
- `[queries.x].connection` unknown → `[ERR]` (rule 4).
- A rule-2/3/7 violation (e.g. `default_database` not in `databases`) is caught at
  **load** as a model `ValidationError` and reported via the existing parse-error
  row — assert it is *not* silently accepted, and that no bespoke 2/3/7 row is
  emitted.
- Single-target legacy config → new rows PASS, no behaviour change.
- Regenerate/adjust `tests/cli/fixtures/verify_snapshot.txt` if ordering changes.

## LLM PROMPT
> Implement Step 13 from `pr_info/steps/step_13.md` (context in
> `pr_info/steps/summary.md`). Add the cross-file static checks (rules 1/4/5/6) to
> `verification/config_files.py` as ordered result rows with no database access,
> recomputing `overall_ok`. Do **not** add rows for rules 2/3/7 — those are
> enforced by the Step 3 model validators at load and have no reachable `[ERR]`
> path; a model `ValidationError` on load must surface through the existing
> config-parse error row instead. Write tests first (valid multi config passes;
> unknown connection, bad per-query database/connection each `[ERR]`; a
> `default_database`/cardinality/legacy-conflict violation is caught at load;
> single-target legacy unchanged) and update the verify snapshot fixture if
> ordering shifts. Run pylint, pytest (`-n auto` + unit markers), mypy,
> lint-imports/tach; all green. One commit.
