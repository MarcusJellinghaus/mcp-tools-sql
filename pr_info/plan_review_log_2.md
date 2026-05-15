# Plan Review Log 2 — Issue #8 (validate_sql)

Second supervisor run. Plan was previously reviewed and updated across two rounds (see `plan_review_log_1.md`). This run starts a fresh `/plan_review` and loops until a round produces zero plan changes.

## Round 1 — 2026-05-15

**Findings** (from engineer's `/plan_review`):
- F1 — Step 3a creates a real circular-import cycle: `_PROGRAMMATIC_BUILTIN_TOOLS` lives in `server.py`, but `schema_tools.load_default_queries()` is told to import it; `server.py` already imports from `schema_tools.py` at module top
- F2 — Step 3a's TOML-collision unit test plumbing is undefined: `load_default_queries()` has a hardcoded path, no injection seam specified
- F3 — Step 1 SQLite test bullet "Calling `get_isolated_connection()` … triggers lazy `connect()`" is imprecise — lazy connect fires on `__enter__`, not on the bare call
- F4 — Empty-tuple splat `*_PYODBC_ERROR` in `except` clause may trip mypy/pylint and is fragile
- F5 — Pre-flight does not reject pure-punctuation inputs (e.g. `";"`); plan's "defence-in-depth" framing oversells coverage
- F6 — Step 3b's "arrange: mssql_db fixture → backend, schema" understates that the fixture yields `MSSQLTestEnv(config, schema)`; implementer must build the backend

**Decisions** (supervisor triage):
- F1 → accept (blocker — lift tuple into `schema_tools.py`)
- F2 → accept (add optional `path: Path | None = None` parameter to `load_default_queries()`; test uses `tmp_path`)
- F3 → accept (wording fix)
- F4 → accept (pre-build `_INVALID_SQL_EXC` module constant)
- F5 → accept lightly (soften prose only; no new tests/behaviour)
- F6 → accept (wording fix — fixture yields a wrapper)

**User decisions:** none — no design questions; all six are straightforward improvements.

**Changes applied:**
- C1 — `step_3a.md` + `summary.md`: `_PROGRAMMATIC_BUILTIN_TOOLS` definition moved to `schema_tools.py`; `server.py` imports it from there; hedging "acceptable cycle" paragraph rewritten; WHERE / WHAT / ALGORITHM / LLM prompt updated
- C2 — `step_3a.md` + `summary.md`: documented optional `path` parameter on `load_default_queries()`; rewrote collision-skip test bullet to use `tmp_path` injection; updated LLM prompt
- C3 — `step_1.md`: reworded the third SQLite bullet to specify lazy `connect()` fires on `__enter__`
- C4 — `step_2.md`: added module-level `_INVALID_SQL_EXC: tuple[type[BaseException], ...] = (sqlite3.Error, *_PYODBC_ERROR)`; ladder uses `except _INVALID_SQL_EXC as exc:`; HOW section explains the rationale
- C5 — `step_2.md`: softened HOW prose to acknowledge pure-punctuation inputs fall through to backend's syntax-error path (correct fallback)
- C6 — `step_3b.md`: ALGORITHM + HOW reflect that `mssql_db` yields `MSSQLTestEnv(config, schema)` and the implementer constructs `MSSQLBackend(env.config)` themselves

**Files changed:**
- `pr_info/steps/step_1.md`
- `pr_info/steps/step_2.md`
- `pr_info/steps/step_3a.md`
- `pr_info/steps/step_3b.md`
- `pr_info/steps/summary.md`

**Status:** changes applied; commit pending.

## Round 2 — 2026-05-15

**Findings** (from fresh engineer's `/plan_review`): none — plan is ready.

The round-1 fixes (C1–C6) all landed cleanly:
- `_PROGRAMMATIC_BUILTIN_TOOLS` consistently described as living in `schema_tools.py` across `summary.md` and `step_3a.md`; `server.py` imports it from there; no circular import remains
- `load_default_queries(path: Path | None = None)` signature is consistent; collision test uses `tmp_path` injection
- Step 1's SQLite test bullet correctly states lazy `connect()` fires on `__enter__`
- `_INVALID_SQL_EXC` module-level constant is defined and used in the exception ladder; HOW explains the rationale
- Step 2 HOW correctly acknowledges pure-punctuation inputs fall through to the backend's syntax-error path
- Step 3b's HOW and ALGORITHM correctly describe `mssql_db` as yielding `MSSQLTestEnv(config, schema)` with implementer-built backend

Internal consistency checks pass: `ValidationTools(backend, backend_name)` constructor identical across files, registration order `SchemaTools` → `ValidationTools` matches between WHAT and ALGORITHM, test bullets agree with implementation snippets, seed-data invariants (customer id 999 absent) are valid.

**Decisions:** none — no findings.

**User decisions:** none.

**Changes applied:** none.

**Files changed:** none (only this log entry).

**Status:** no plan changes needed.

## Final Status

Two rounds in this supervisor session.

- **Round 1** — six findings, all autonomously triaged and applied (no user decisions required). Committed as `42e248f` — `docs(plan): apply round-2 plan-review fixes for validate_sql`.
- **Round 2** — zero findings. Loop terminates.

The plan is ready for implementation approval. No outstanding design questions; all decisions captured in `pr_info/steps/Decisions.md`. Steps are 1 → 2 → 3a → 3b, each producing exactly one commit and leaving the codebase with passing checks.
