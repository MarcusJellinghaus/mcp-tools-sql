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
