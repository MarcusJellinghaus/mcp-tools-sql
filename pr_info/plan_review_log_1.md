# Plan Review Log — Issue #8 (validate_sql)

## Round 1 — 2026-05-14

**Findings** (from engineer's `/plan_review`):
- F1 — Pre-flight error strings use `Error:` lead-in, conflicting with Decision #9
- F2 — Missing-param error formatted differently (`KeyError: '<n>'`) from other pre-flight errors
- F3 — Step 2 MSSQL `_explain` branch ships untested by Step 2; only exercised by Step 3 integration
- F4 — Step 3 bundles server wiring + 8 MSSQL integration tests in one commit
- F5 — Test boundary between Step 2 (manual register) and Step 3 (server.py path) implicit
- F6 — `caplog` assertion on `builtin_tools=<N>` may be infeasible against `run_server` surface
- F7 — `sqlparse.tokens.Comment` subtype matching (already correctly phrased — implementer note)
- F8 — `params=None` + parameterised SQL not explicitly tested in pre-flight
- F9 — `builtin_tools` counter could use a tuple for scalability
- F10 — No collision policy if `default_queries.toml` defines `validate_sql`
- F11 — Step 1 commit message — no change
- F12 — Ruff / lint-imports / bandit not in per-step "Run before commit" lists

**Decisions** (supervisor triage):
- F1, F2 → ask user (design question — format policy)
- F3 → ask user (coverage gap; should-fix)
- F4 → ask user (granularity)
- F5 → accept (formatting clarification)
- F6 → accept (soften assertion with fallbacks)
- F7, F11, F12 → skip
- F8 → accept (test detail)
- F9 → accept (KISS-friendly tuple)
- F10 → ask user (policy)

**User decisions:**
- Q1 (pre-flight error prefix) → Option C: synthetic `ValidationError:` prefix for pre-flight; Decision #9 carves out pre-flight rejection vs exception-bucketed errors.
- Q2 (Step 2 MSSQL coverage) → Add mocked `_explain` unit test (recommended).
- Q3 (Step 3 granularity) → Split into 3a (server wiring + server-registration test + TOML collision skip) and 3b (MSSQL integration tests).
- Q5 (TOML name collision) → Reserve programmatic-builtin names; skip TOML entry with a warning log on collision.

**Changes applied (C1–C8):**
- C1 — Pre-flight error strings rewritten to `Invalid SQL. ValidationError: <reason>` and `Invalid parameters. ValidationError: missing parameter: <name>` in `step_2.md`. `Decisions.md` created with Decision #8 (never re-raise) and Decision #9 (synthetic-vs-real ExcType policy).
- C2 — Added mocked MSSQL `_explain` unit test to `step_2.md` Tests section.
- C3 — Split `step_3.md` into `step_3a.md` and `step_3b.md`. `summary.md` step ordering updated.
- C4 — Test-boundary clarifications added to `step_2.md` preamble and `step_3a.md` server-registration test.
- C5 — `caplog` assertion in `step_3a.md` softened with fallback options.
- C6 — Two pre-flight test variants added (`params=None` and `params={}`) for parameterised SQL in `step_2.md`.
- C7 — `_PROGRAMMATIC_BUILTIN_TOOLS = ("validate_sql",)` tuple + `len(...)` counter described in `step_3a.md` and `summary.md`.
- C8 — TOML loader collision-skip logic + unit test described in `step_3a.md`; `summary.md` Modified list updated.

**Files changed:**
- `pr_info/steps/summary.md` (updated)
- `pr_info/steps/step_2.md` (updated)
- `pr_info/steps/step_3.md` (deleted)
- `pr_info/steps/step_3a.md` (new)
- `pr_info/steps/step_3b.md` (new)
- `pr_info/steps/Decisions.md` (created)
- `pr_info/plan_review_log_1.md` (new — this file)

**Tooling note:** `mcp-workspace` MCP server was not available; engineer used native file tools as fallback per supervisor instructions.

**Status:** changes applied; commit pending.
