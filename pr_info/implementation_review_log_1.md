# Implementation Review Log — Issue #38

`count_records` tool + sqlparse → sqlglot migration.

Supervisor: technical lead (delegates all implementation to engineer subagents).
Started: 2026-06-25.

---

## Round 1 — 2026-06-25

**Findings** (from `/implementation_review`):
- Checks all green: pytest 522 passed / 16 skipped / **0 failed**, pylint ✓, mypy ✓, ruff ✓, import-linter ✓.
- Key judgment: the failures the TASK_TRACKER step notes called "pre-existing" were in fact regressions this branch's Step 1 introduced; final commit `d2f42ec` fixed all of them. Suite is green. Not acceptable-debt and no longer present.
- Correctness: sqlglot migration sound; `validate_sql` preflight rejections (empty/multi/missing-param/fail-closed ParseError + USE/SET/DECLARE) preserved; read-only AST gate correctly fail-closed (write nodes, SELECT…INTO, data-modifying CTEs, non-readonly roots); SQLite fresh `PRAGMA query_only=ON` connection and MSSQL leading-WITH rejection correct. No Critical findings.
- A1: `tach.toml` over-declares `count_tools` `depends_on` (lists `formatting`/`tool_builder` not actually imported; templated from `validation_tools`).
- A2: `count_records` re-parses SQL up to 4× per call (correct, cheap, non-hot).
- A3: TASK_TRACKER step notes stale (describe now-fixed failures).
- S1/S2: intentional exception-mapping pattern + spike tests gating sqlglot assumptions.

**Decisions**:
- A1 → **Accept**. Bounded architecture-config hygiene; repo treats tach/import-linter as first-class. Trim to actual imports.
- A2 → **Skip**. Speculative perf on a non-hot validation path; YAGNI.
- A3 → **Skip**. `pr_info/` is deleted later; "don't worry about" per knowledge base.
- S1/S2 → **Skip**. Intentional, consistent with `validate_sql`.

**Changes**: A1 — trimmed `tach.toml` `count_tools.depends_on` to `{backends, tool_logging, utils}` (removed `config`/`formatting`/`tool_builder`). tach ✓, lint-imports ✓.
**Status**: committed `75c9d2e` (tach.toml only).

## Round 2 — 2026-06-25

**Findings**: Follow-up verification after the `75c9d2e` config trim. All checks green — pytest 522 passed / 16 skipped / **0 failed**, pylint ✓, mypy ✓, ruff ✓, tach `[]`, lint-imports 2 kept / 0 broken. `count_tools` `depends_on` now matches actual imports exactly. No new findings.
**Decisions**: none — branch healthy.
**Changes**: none.
**Status**: no changes needed → loop exits.

## Final Status

- **Rounds**: 2 (Round 1 found + fixed A1; Round 2 verified clean with zero code changes → loop exit).
- **Commits this review**: `75c9d2e` Trim count_tools tach dependencies to actual imports.
- **Quality gates** (supervisor-run): vulture — no output; lint-imports — 2 contracts kept, 0 broken.
- **Engineer-run checks**: pytest 522 passed / 16 skipped / 0 failed, pylint ✓, mypy ✓, ruff ✓, tach ✓.
- **Outcome**: No Critical findings. The single accepted finding (tach over-declaration) is fixed. The "pre-existing failures" noted in TASK_TRACKER were regressions introduced and already resolved within this branch (`d2f42ec`); the suite is fully green. Implementation aligns with the issue and summary.md.
- **Remaining**: PR-section tasks in TASK_TRACKER (PR review tick, PR summary). No code work outstanding.
