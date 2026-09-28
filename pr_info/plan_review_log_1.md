# review-plan review log 1

## Round 1 — 2026-09-28
**Findings**:
I'll gather context first.Confirmed. Findings:

`pr_info/steps/summary.md:173` — medium — claims steps 3 and 6 are "independent of everything else and could move", contradicting `summary.md:136` and `step_6.md:6`: step 6 consumes `make_warn_entry`, which step 5 creates, so step 6 cannot precede step 5.

`pr_info/steps/step_3.md:64` — medium — the fan-out test criterion ("a tool call must succeed") false-passes: `build_schema_body`'s fan-out wraps each target's execute in `except Exception` (`query_helpers.py:350`), so a stub raising from `execute_query` returns a formatted string with an inline per-target error rather than failing. The test must assert the returned rows and the absence of inline error text.

`pr_info/steps/step_2.md:107` — medium — decision 1's regression (gate fires regardless of `allow_updates`) is left optional ("add the test only if a wiring path makes it meaningful, otherwise skip it"). `create_server(..., allow_updates=True)` is a real, cheap wiring path; the issue's headline claim ends up with no test.

`pr_info/steps/step_5.md:49` — medium — placing the `read_only` rows after `<name>.sql` means `verify` computes and sends the `EXPLAIN` of operator-authored non-read-only SQL to the database before any read-only verdict exists; computing the verdict first and short-circuiting the EXPLAIN is cheaper and matches the issue's intent.

`pr_info/steps/step_7.md:38` — medium — the boy-scout caption fix is half-done: the sample rows are labelled `read_schemas.*`, a *default* query (`src/mcp_tools_sql/default_queries.toml:1`) that can never appear in QUERIES, so correcting the caption at `docs/cli.md:276` while keeping those labels leaves the sample self-contradictory.

`pr_info/steps/step_7.md:12` — medium — no doc coverage for the two new `[WARN]` cases: `docs/cli.md:229-231` still describes WARN as "most common case is sensitive keys", and the `CONNECTION` description at `docs/cli.md:221` lists the path check without the `:memory:` warning (step 6) or the unknown-backend row (step 5).

`pr_info/steps/step_5.md:18` — low — `make_warn_entry` duplicates `make_skipped_entry`'s `ok=True` + post-set `warn` construction (`verification/_helpers.py:37-50`); the plan should have `make_skipped_entry` delegate to the new helper rather than leaving two warn-entry constructions.

`pr_info/steps/step_5.md:56` — low — only `verify_one_query`'s docstring is slated for update; `verify_queries`' docstring (`verification/queries.py:155-157`) also states "three rows per query".

`pr_info/steps/step_2.md:76` — low — the gate calls `to_dialect(target.backend_name)` unguarded while step 5 guards the identical call; the plan should record why it is safe here (`backend_for` runs `create_backend`, which already rejects unmappable backend names) so the implementer does not "fix" the asymmetry.
**Decisions**:
Verdict(decision='tasks', tasks=['step_3.md:64 — replace the fan-out acceptance criterion: since build_schema_body swallows per-target exceptions into an inline error string, the test must assert the expected rows are present AND that no inline per-target error text appears, not merely that the call succeeds.', "step_2.md:107 — make decision 1's regression test mandatory, not optional: specify a test that builds the server via create_server(..., allow_updates=True) and asserts the non-SELECT gate still rejects, so the issue's headline claim is covered.", 'step_7.md:12 — extend the doc task to cover the two new [WARN] cases: update docs/cli.md:229-231 so WARN is no longer described as only sensitive keys, and add the :memory: warning (step 6) and the unknown-backend row (step 5) to the CONNECTION description at docs/cli.md:221.', 'step_7.md:38 — finish the caption fix: the docs/cli.md:276 sample labels rows as read_schemas.*, a default query that can never appear in QUERIES; relabel the sample rows to a QUERIES-sourced name so the corrected caption and the sample agree.'], escalate_reason=None)
**Changes**:
applied

## Round 2 — 2026-09-28
**Findings**:
I'll gather context first.`pr_info/steps/summary.md:148` — medium — the tests table says `tests/cli/test_verify.py`'s `execute_query` side effect is "retargeted" in step 3, contradicting `step_3.md:70` and decision 9, which keep the `SELECT 1` probe on `execute_query`; an implementer following the summary would break decision 9.

`pr_info/steps/summary.md:173` — medium — "Steps 3 and 6 are independent of everything else and could move" contradicts `step_6.md:8`: step 6 consumes `make_warn_entry`, created in step 5, so step 6 cannot precede step 5.

`pr_info/steps/step_5.md:49` — medium — placing the `read_only` rows after `<name>.sql` means `verify` EXPLAINs operator-authored non-read-only SQL against the database before any read-only verdict exists; computing the verdict first and short-circuiting the EXPLAIN is cheaper and matches the issue's intent.

`pr_info/steps/step_5.md:56` — low — only `verify_one_query`'s docstring is slated for update; `verify_queries`' docstring (`verification/queries.py:155-157`) also states "three rows per query".

`pr_info/steps/step_5.md:18` — low — `make_warn_entry` duplicates `make_skipped_entry`'s `ok=True` + post-set `warn` construction (`verification/_helpers.py:44-50`); have `make_skipped_entry` delegate to the new helper rather than leaving two warn-entry constructions.

`pr_info/steps/step_2.md:77` — low — the gate calls `to_dialect(target.backend_name)` unguarded while `step_5.md:43` guards the identical call; record here why it is safe (`registry.backend_for` runs `create_backend`, which already rejects unmappable backend names) so the implementer does not "fix" the asymmetry.

`pr_info/steps/step_2.md:20` — low — `read_only_rejection` is a pure SQL-analysis wrapper over two `utils/sql_placeholders.py` primitives but is planned into `query_helpers.py`; `sql_placeholders.py` is already edited in step 1 and is the cohesive home, and it would drop the new `verification → query_helpers` coupling rationale from the summary.
**Decisions**:
Verdict(decision='tasks', tasks=['summary.md:148 — fix the tests table row for tests/cli/test_verify.py: it must not say the execute_query side effect is "retargeted" in step 3; align it with step_3.md:70 and decision 9, which keep the SELECT 1 probe on execute_query.'], escalate_reason=None)
**Changes**:
applied

## Round 3 — 2026-09-28
**Findings**:
I'll gather context first.No critical or high findings; the plan matches the codebase facts I verified (call sites, signatures, fixtures, test idioms) and covers every issue requirement.

`pr_info/steps/summary.md:173` — medium — "Steps 3 and 6 are independent of everything else and could move" contradicts `step_6.md:8` and the file table at `summary.md:136`: step 6 consumes `make_warn_entry`, which step 5 creates, so step 6 cannot precede step 5.
**Decisions**:
Verdict(decision='dismiss', tasks=[], escalate_reason=None)
**Changes**:
dismiss
