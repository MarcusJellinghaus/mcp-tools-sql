# Step 14 — verify: per-target M2 (QUERIES/UPDATES) + skip rows + snapshot

See `pr_info/steps/summary.md` → "verify" (decision 25). Builds on the CONNECTION
per-pair probing + orchestrator registry migration from Step 13.

## WHERE
- `src/mcp_tools_sql/verification/queries.py`, `updates.py`, `orchestrator.py`
- Tests: `tests/verification/test_queries.py`, `test_updates.py`,
  `test_orchestrator.py`, `tests/cli/test_verify.py`
- Fixture: `tests/cli/fixtures/verify_snapshot.txt` — the QUERIES + UPDATES
  byte-for-byte snapshot asserted by `test_verify_cli_queries_updates_snapshot`.
  This step reworks M2 rendering, so regenerate the fixture to the new per-target
  row wording.

## WHAT
- M2: each query/update EXPLAINed against **its own** resolved target; queries
  whose target is unreachable are reported as skipped **naming the connection**,
  not blanked.
- `verify_queries` / `verify_updates` gain `targets` + `registry` + a
  `reachable` map (from Step 13's CONNECTION probes); per entry, resolve its
  pinned target, and if that target's connection probe failed, emit a
  `skipped (connection <name> unreachable)` row instead of EXPLAINing.
- Orchestrator threads `targets`, `registry`, and the `reachable` map into M2,
  replacing the single-`default` backend it passed in Step 13.

## HOW
- Step 13 already builds `ResolvedTargets` + `BackendRegistry` and records a
  per-pair reachability result while probing CONNECTION. Capture that as
  `reachable: dict[(conn, db), bool]` and pass it to M2.
- Per query/update: `target = targets.resolve_pinned(cfg.connection or None,
  cfg.database or None)`; if `reachable[(target.connection, target.database)]` is
  False, emit the skip row; else EXPLAIN against `registry.backend_for(target)`.

## ALGORITHM (orchestrator M2)
```
reachable = {}                      # (conn,db) -> ok, from CONNECTION probes (Step 13)
for t in targets.targets: probe -> CONNECTION rows; reachable[key] = ok
verify_queries(qcfg.queries, targets, registry, reachable)   # per-target EXPLAIN/skip
verify_updates(qcfg.updates, targets, registry, reachable)
# registry.close_all() in the orchestrator finally (already present from Step 13)
```

## DATA
M2 rows are either real EXPLAIN verdicts or per-connection skip rows. Skip
summary wording updated to mention unreachable connections.

## TESTS (write first)
- A query pinned to an unreachable connection → skip row naming that connection;
  a reachable query in the same run still gets a real verdict (not blanked).
- Single-target config → M2 output equivalent to today (one reachable pair).
- Two databases on one connection, a query pinned to each → each EXPLAINed
  against its own target.
- `test_verify_cli_queries_updates_snapshot`: regenerate
  `tests/cli/fixtures/verify_snapshot.txt` to the new per-target QUERIES/UPDATES
  row wording and confirm the CLI stdout matches it byte-for-byte.

## LLM PROMPT
> Implement Step 14 from `pr_info/steps/step_14.md` (context in
> `pr_info/steps/summary.md`). Rework verify M2 so `verify_queries` /
> `verify_updates` take `(scope, targets, registry, reachable)` and resolve each
> query/update to its own pinned target — EXPLAINing reachable targets and
> emitting per-connection skip rows for unreachable ones instead of blanking M2.
> Thread the reachability map from Step 13's CONNECTION probes through the
> orchestrator. Keep single-target output equivalent to today. Regenerate the
> verify snapshot fixture to the new wording. Write tests first. Run pylint,
> pytest (`-n auto` + unit markers), mypy, lint-imports/tach; all green. One
> commit.
