# Plan Review Log — Run 2

Issue: #9 — CLI: init and verify commands
Branch: 9-cli-init-and-verify-commands
Started: 2026-05-01

## Round 1 — 2026-05-01

**Findings**:
- Step 8: `_check_sql_explain` calls `backend.explain(sql, dummy_params)` but `DatabaseBackend.explain(self, sql)` ABC and `SQLiteBackend.explain` only take `sql` — real bug.
- Step 7: `verify_connection` returns `(result_dict, open_backend_or_None)` but the open-backend `try/finally` lifecycle was deferred to step 8's orchestrator wiring.
- Step 6 + summary.md: `verify_builtin()` signature drift — summary says no args, step 6 says `backend_name: str`. Also "factor out `compute_mounted_tools`" framing is premature given no filtering exists yet.
- Step 4: `_run_pyproject` silently drops `args.output`; spec is silent on the interaction.
- Step 3a: doesn't note replacement of `main.py`'s no-op `_setup_logging` placeholder with real `setup_logging` from `utils.log_utils`.
- Step 9: schema-fallback caveat needs documenting (no `dbo`/`public` default; empty schema → `[ERR]`).
- Step 8 `_LEGITIMATE_NON_SQL_PARAMS` allow-list — flagged for confirmation (acceptable for v1).
- All issue tests (i)–(xiv) mapped to steps with no gaps. Verdict: minor tweaks needed.

**Decisions**:
- Accept (auto): step 8 `explain()` signature widening (ABC + SQLite, `params: dict | None = None`); step 7 try/finally wiring moved into step 7; step 6 keep `verify_builtin()` no-args + `tools_registered_count = len(load_default_queries())`; step 4 document `--output` ignored under `--pyproject`; step 3a swap placeholder for real `setup_logging`; step 9 schema-fallback note.
- Skip: step 2 grep scope (already correct), step 8 allow-list (acceptable for v1).
- Ask user: tools_registered_count scope (Q1 — count vs. extract helper vs. introduce filtering now).

**User decisions**:
- Q1 (tools_registered_count scope): **Option A** — count = `len(load_default_queries())`; no helper extraction; defer real filtering to a future PR when disabled/per-backend filtering is actually introduced.

**Changes**:
- `pr_info/steps/step_3a.md` — replace placeholder `_setup_logging` with imported `setup_logging` from `mcp_tools_sql.utils.log_utils`.
- `pr_info/steps/step_4.md` — note `--output` ignored under `--pyproject` (debug log).
- `pr_info/steps/step_6.md` — `verify_builtin()` no-args; one-liner `len(load_default_queries())`; drop helper extraction.
- `pr_info/steps/step_7.md` — own backend close lifecycle (try/finally wiring).
- `pr_info/steps/step_8.md` — new "Backend signature widening" section; `DatabaseBackend.explain` / `SQLiteBackend.explain` widened to `(sql, params=None)`; lifecycle deferred to step 7.
- `pr_info/steps/step_9.md` — schema-fallback caveat clarified as intended behavior.
- `pr_info/steps/Decisions.md` — appended Round 2 decisions section.

**Status**: committed (`5df09a6`) and pushed.

## Round 2 — 2026-05-01

**Findings**:
- All round-1 fixes verified applied correctly to step files and `Decisions.md`. No regressions or stale references.
- Step 8: `_check_sql_explain` HOW section still contains old `SET SHOWPLAN_TEXT ON/OFF` example with `backend._connection` reach-in — dead narrative now that the final algorithm uses `backend.explain(sql, params)`.
- Step 8: WHERE list could be misread as if a third backend file (mssql) is being modified.
- Step 3a: no explicit note that the `args.command == "server"` branch stays `NotImplementedError` (out of scope for #9).
- Coverage matrix (i)–(xiv) intact. Final compliance matrix retained at end of step 9.
- Verdict: plan ready for approval; only nice-to-have polish.

**Decisions**:
- Accept (auto) all three polish items: trim SHOWPLAN narrative in step 8, add "mssql.py not modified" line, clarify `server` branch out of scope in step 3a.
- No design/requirements questions raised.

**User decisions**: none required.

**Changes**:
- `pr_info/steps/step_8.md` — collapsed `_check_sql_explain` HOW to final algorithm only; added "mssql.py — not modified" line under WHERE.
- `pr_info/steps/step_3a.md` — note that `server` branch keeps raising `NotImplementedError` for #9.

**Status**: committed (`1c305e0`) and pushed.

## Round 3 — 2026-05-01

**Findings**:
- Round-2 fixes verified applied correctly (SHOWPLAN trim, "mssql.py not modified" line, `server` branch out of scope).
- All prior decisions (round-1 explain widening, step-7 try/finally, step-6 minimal scope, step-4 `--output` note, step-3a real `setup_logging`, step-9 schema fallback) confirmed present in step files.
- Coverage matrix (i)–(xiv) intact; final compliance matrix retained at end of step 9.
- Stylistic nits noted (unused `_EXPLAIN_PREFIX["mssql"]` entry, duplicate sensitive-keys deferral wording) — not raised.
- Verdict: plan ready for approval — zero changes.

**Decisions**: no plan edits required this round.

**User decisions**: none required.

**Changes**: none.

**Status**: convergence reached.

## Final Status

- **Rounds run**: 3 (Round 1: substantive fixes; Round 2: minor polish; Round 3: zero changes — converged).
- **Commits produced**:
  - `5df09a6` — `docs(plan): finalize #9 plan with round-1/round-2 review fixes`
  - `1c305e0` — `docs(plan): trim stale SHOWPLAN narrative and clarify out-of-scope branches`
  - (this log finalization commit, see git log)
- **User decisions made**: 1 — Q1 (`tools_registered_count` scope): keep minimal `len(load_default_queries())`, no helper extraction.
- **Plan readiness**: ready for approval. All 14 issue tests (i)–(xiv) mapped to steps; no contradictions between `summary.md`, `Decisions.md`, and step files; round-1 + round-2 fixes verified applied.
