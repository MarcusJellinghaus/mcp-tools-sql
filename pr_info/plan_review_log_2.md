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

**Status**: changes pending commit.

