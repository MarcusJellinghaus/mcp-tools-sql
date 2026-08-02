# Step 13 — verify: per-pair CONNECTION + per-target M2 + exit code

See `pr_info/steps/summary.md` → "verify" (decisions 24, 25).

## WHERE
- `src/mcp_tools_sql/verification/connection.py`, `queries.py`, `updates.py`,
  `orchestrator.py`
- Tests: `tests/verification/test_connection.py`, `test_queries.py`,
  `test_updates.py`, `test_orchestrator.py`

## WHAT
- CONNECTION: probe **every** `(connection, database)` pair. One sub-section /
  row-group per pair; `database` row becomes the per-pair catalog under test.
- M2: each query/update EXPLAINed against **its own** resolved target; queries
  whose target is unreachable are reported as skipped **naming the connection**,
  not blanked.
- Exit code non-zero if any connection fails (already derived from `overall_ok`
  across sections — confirm it holds per-pair).

## HOW
- Orchestrator builds `ResolvedTargets` (via `resolve_targets`) and a
  `BackendRegistry`, replacing `_resolve_connection_for_verify`. It closes the
  registry in `finally`.
- `verify_connection(target, backend)` verifies one pair using the registry's
  backend (rename param from `connection` to `target`; use `target.config`).
  Loop it over `targets.targets`, prefixing row keys with the pair label.
- `verify_queries`/`verify_updates` gain the `targets` + `registry`; per entry,
  resolve its pinned target, and if that target's connection probe failed, emit a
  `skipped (connection <name> unreachable)` row instead of EXPLAINing.

## ALGORITHM (orchestrator M2)
```
targets = resolve_targets(qcfg, dbcfg); registry = BackendRegistry()
reachable = {}                      # (conn,db) -> ok, from CONNECTION probes
for t in targets.targets: probe -> CONNECTION rows; reachable[key]=ok
verify_queries(qcfg.queries, targets, registry, reachable)   # per-target EXPLAIN/skip
verify_updates(...)  ; finally registry.close_all()
```

## DATA
CONNECTION result dict keyed per pair (e.g. `prod/sales.select_1`); M2 rows either
real EXPLAIN verdicts or per-connection skip rows. Skip summary wording updated to
mention unreachable connections.

## TESTS (write first)
- Two databases on one connection → CONNECTION probes both; both `select_1` rows
  present.
- A query pinned to an unreachable connection → skip row naming that connection;
  a reachable query in the same run still gets a real verdict (not blanked).
- Single-target config → CONNECTION/M2 output equivalent to today (one pair).
- Exit code non-zero when any pair fails.

## LLM PROMPT
> Implement Step 13 from `pr_info/steps/step_13.md` (context in
> `pr_info/steps/summary.md`). Rework the verify CONNECTION + M2 flow to probe
> every `(connection, database)` pair (via `resolve_targets` + `BackendRegistry`,
> closed in `finally`) and resolve each query/update to its own target, emitting
> per-connection skip rows for unreachable targets instead of blanking M2. Keep
> single-target output equivalent to today and the exit code non-zero on any
> failure. Write tests first. Run pylint, pytest (`-n auto` + unit markers), mypy,
> lint-imports/tach; all green. One commit.
