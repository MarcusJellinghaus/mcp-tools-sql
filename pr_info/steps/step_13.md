# Step 13 — verify: per-pair CONNECTION probing + orchestrator registry migration

See `pr_info/steps/summary.md` → "verify" (decision 24). This step reworks only
the CONNECTION section and the orchestrator's resolver; the per-target M2
(QUERIES/UPDATES) rework is Step 14, so M2 rendering — and the verify snapshot —
stay byte-identical here.

## WHERE
- `src/mcp_tools_sql/verification/connection.py`, `orchestrator.py`
- `src/mcp_tools_sql/config/loader.py` (delete dead `resolve_connection`)
- Tests: `tests/verification/test_connection.py`, `test_orchestrator.py`,
  `tests/config/test_loader.py`, `tests/cli/test_verify.py`

## WHAT
- CONNECTION: probe **every** `(connection, database)` pair. One sub-section /
  row-group per pair; `database` row becomes the per-pair catalog under test.
- Orchestrator builds `ResolvedTargets` (via `resolve_targets`) and a
  `BackendRegistry`, replacing `_resolve_connection_for_verify`; it closes the
  registry in `finally`.
- **M2 unchanged in this step.** `verify_queries` / `verify_updates` keep their
  current single-`open_backend` signature, fed `registry.backend_for(targets.default)`
  so the QUERIES/UPDATES rendering (and its snapshot) stay byte-identical. The
  reachability map + per-target resolution + skip rows land in Step 14.
- Exit code non-zero if any connection fails (already derived from `overall_ok`
  across sections — confirm it holds per-pair).
- **Dead-code cleanup (same commit).** Step 6 migrated `server.py` off
  `resolve_connection`, and this step replaces `_resolve_connection_for_verify`
  in `orchestrator.py`. With no production callers left, **delete both
  `resolve_connection` (`config/loader.py`) and `_resolve_connection_for_verify`
  (`orchestrator.py`)** and drop their now-orphaned tests in
  `tests/config/test_loader.py` — no legacy artifacts. (Before deleting, grep to
  confirm no other production caller remains; `resolve_targets` is the sole
  resolver going forward.)

## HOW
- `verify_connection(target, backend)` verifies one pair using the registry's
  backend (rename param from `connection` to `target`; use `target.config`).
  Loop it over `targets.targets`, prefixing row keys with the pair label.
- Orchestrator: `targets = resolve_targets(qcfg, dbcfg); registry = BackendRegistry()`;
  probe each pair; pass `registry.backend_for(targets.default)` to the still-
  unchanged `verify_queries` / `verify_updates`; `registry.close_all()` in
  `finally`.

## ALGORITHM (orchestrator)
```
targets = resolve_targets(qcfg, dbcfg); registry = BackendRegistry()
try:
    for t in targets.targets: probe -> CONNECTION rows (verify_connection(t, registry.backend_for(t)))
    verify_queries(qcfg.queries, registry.backend_for(targets.default))   # unchanged M2
    verify_updates(qcfg.updates, registry.backend_for(targets.default))
finally: registry.close_all()
```

## DATA
CONNECTION result dict keyed per pair (e.g. `prod/sales.select_1`). M2 rows and
the verify snapshot are unchanged in this step.

## TESTS (write first)
- Two databases on one connection → CONNECTION probes both; both `select_1` rows
  present.
- Single-target config → CONNECTION output equivalent to today (one pair).
- Exit code non-zero when any pair fails.
- `resolve_connection` / `_resolve_connection_for_verify` removed; grep confirms
  no remaining caller and their orphaned tests are dropped.
- `test_verify_cli_queries_updates_snapshot` still passes **unchanged** — M2 is
  not reworked here, so the fixture must stay byte-for-byte identical (proves the
  CONNECTION rework did not leak into M2).

## LLM PROMPT
> Implement Step 13 from `pr_info/steps/step_13.md` (context in
> `pr_info/steps/summary.md`). Rework the verify CONNECTION section to probe every
> `(connection, database)` pair via `resolve_targets` + `BackendRegistry` (closed
> in `finally`), renaming `verify_connection`'s param to `target`. Keep M2
> (QUERIES/UPDATES) untouched by feeding it `registry.backend_for(targets.default)`
> so the snapshot stays identical. Delete the now-dead `resolve_connection` and
> `_resolve_connection_for_verify` and their orphaned tests. Keep single-target
> output equivalent to today and the exit code non-zero on any failure. Write
> tests first. Run pylint, pytest (`-n auto` + unit markers), mypy,
> lint-imports/tach; all green. One commit.
