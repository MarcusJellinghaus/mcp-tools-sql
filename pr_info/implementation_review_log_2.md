# Implementation review log 2 — issue #62

Round 1 (log 1) ended on a rebase escalation; its two findings were never
implemented. This log continues the review from there.

## Round 1 — 2026-09-29

**Findings**

- C1 (high) `query_helpers.py:98` — `read_only_rejection` catches only `ParseError`;
  sqlglot raises the sibling `TokenError` for unterminated literals, comments and
  brackets, so it escapes `QueryTools.register` and `verification/queries.py`.
- C2 (high) `count_tools.py:138`, `summarize/source.py:391`, `summarize/sql.py:206` —
  the new `passthrough_source_violation` guard is not applied on the caller-facing
  arbitrary-SQL paths, leaving the `OPENQUERY` write hole open there.
- S1 `query_helpers.py:98` — the verdict parses the same SQL three times.
- S2 `tests/cli/fixtures/verify_snapshot.txt:6` — the snapshot bakes in sqlglot's
  own error wording.
- S3 `verification/connection.py:139` — the `:memory:` check is an exact string match.
- S4 `query_tools.py:68` — `resolve_sql` computed twice.
- S5 `tests/test_server.py:240,267` — function-local import and `protected-access`.
- S6 — branch is behind `origin/main`.

Both round-1 findings from log 1 (ParseError sanitisation, OPENQUERY/OPENROWSET)
were confirmed already fixed.

**Decisions**

- C1 — accept. Real regression against decision 3: one unbalanced quote killed
  server startup. `extract_sql_params` fixed with it, same root cause.
- C2 — escalated to Marcus (scope call: this branch introduces the guard, but the
  hole is on a pre-existing surface). Decision: fix now.
- S3 — accept. One-line widening, catches the equivalent URI spellings.
- S2 — accept. Removes a byte-identical assertion on a third party's error text.
- S1 — skip. Startup and verify only; same input and dialect, so the three cannot
  disagree.
- S4 — skip. Cosmetic; the "gated string is the executed string" constraint holds
  either way.
- S5 — skip. Pre-existing pattern shared with the neighbouring tests.
- S6 — rebase before the PR, not a code change.

**Changes**

- `read_only_rejection` and `extract_sql_params` catch `SqlglotError`; `TokenError`
  now yields a rejection message instead of escaping. Covered on the startup gate,
  the verify row, and the `issubclass` premise itself.
- New shared `arbitrary_sql_violation` (AST proof + pass-through guard) wired into
  `count_records` and both `summarize_columns` gates. `read_only_violation`'s
  verdict logic untouched (decision 10); the absorption guard deliberately stays
  out of the composition, pinned by a test. `count_tools`' overstated Layer-1
  docstring corrected.
- `_is_memory_path` matches `:memory:` and `mode=memory` case-insensitively; row
  stays `ok=True, warn=True` (decision 14).
- Snapshot fixture query changed to `DELETE FROM badtable` and regenerated from
  actual output; no sqlglot-authored text remains.
- Pass-through summarize tests split into `tests/summarize/test_source_passthrough.py`
  to stay under the 750-line limit.

**Deferred**: `basic_preflight` also catches only `ParseError`. Same root cause as
C1, caller-facing rather than startup-fatal. Carried to round 2.

**Status**: format / pylint / pytest (1066 passed, 19 skipped) / mypy / tach /
lint-imports all green. Committed.

## Round 2 — 2026-09-29

**Findings**

- F1 (medium) `utils/sql_placeholders.py:364` — `basic_preflight` still catches only
  `ParseError`, so a `TokenError` escapes out of `count_records`, `validate_sql` and
  both `summarize` paths. Message label hardcodes `ParseError`.
- F2 (low) `utils/sql_placeholders.py:365` — the verdict text carries newlines and
  ANSI escapes; the gate already flattens its own rejection.
- F3 (low) `verification/queries.py:162` — `verify` EXPLAINs a query before computing
  its read-only row, so the row reports the database's complaint (`no such table`)
  rather than the gate's rejection.
- F4 (low) `verification/connection.py:154` — the `:memory:` branch bypasses the
  control-character check.
- F5 (low) `query_tools.py:67` — the backend is resolved one line before the gate, so
  a rejected query still triggers a registry lookup.
- F6 — branch still behind `origin/main`.

No critical issues. The round-1 fixes in `eb0ea0f` were re-verified against the
running sqlglot, not just read: the pass-through guard rejects all three functions
under both dialects and accepts a column merely named `openquery`, and the AST
re-render was confirmed to preserve an `OPENQUERY(...)` call — so wiring the guard
into the caller-facing paths was necessary, not belt-and-braces.

**Decisions**

- F1 — accept. Same root cause as round 1's C1; leaving the third call site narrow
  ships an inconsistent fail-closed parse contract in the branch's own subject area.
- F2 — accept, bundled with F1. One implementation, so `single_line` moves down into
  `utils`.
- F3 — accept. The row was actively misleading about why the query is bad, and the
  verify row is the discoverability mechanism decision 3 relies on.
- F4 — skip. Contrived; the empty-path case is unaffected.
- F5 — skip. Cosmetic micro-optimisation on working code; targets are shared across
  queries.
- F6 — rebase before the PR, not a code change.

**Changes**

- `basic_preflight` catches `SqlglotError` and names the class from the exception, so
  the existing `ParseError` assertions stay green. Parametrized coverage over the
  three untokenizable shapes against `count_records`, `validate_sql`, `validate_source`
  and `summarize`'s `where` path, plus direct unit tests.
- `_ANSI_ESCAPE_RE` and `_single_line` moved from `query_helpers` into `utils` and made
  public as `single_line`, following `verification/_helpers.py`'s stated convention;
  used by both `read_only_rejection` and `basic_preflight`.
- `verify_one_query` computes the read-only verdict first and skips the EXPLAIN probe
  when the pinned variant fails, via a new `make_skipped_not_read_only_entry`
  (`ok=True, warn=True`, so the `read_only` row stays the single source of the failing
  exit code). Snapshot regenerated from captured output; one line changed.
- `test_verify_queries_detects_invalid_sql`'s SQL changed to a parseable missing-table
  SELECT so it still reaches EXPLAIN, plus tests asserting the skip fires on a DELETE /
  ParseError / TokenError and does *not* fire on a clean SELECT.
- `docs/cli.md` QUERIES row describes the new skip.

**Status**: format / pylint / pytest (1089 passed, 19 skipped) / mypy / tach /
lint-imports / check_file_size all green. Committed.

## Round 3 — 2026-09-29

**Findings**

- G1 (medium) `count_tools.py:134`, `summarize/source.py:386`, `summarize/sql.py:209` —
  the fail-closed parse contract misses SQL that tokenizes to *zero* statements.
  `basic_preflight` rejects empty and multi-statement SQL but not `statement_count == 0`,
  so `-- hi`, `/* hi */` and `;` reach `parse_one` and raise `ParseError` out of the tool.
- G2 (low) `docs/cli.md:229` — the closed enumeration of `[WARN]` causes was not extended
  with the fifth cause added by `1004c2b`.
- G3 (low) `utils/sql_placeholders.py:61` — `single_line` is a pure text utility living in
  a module scoped to SQL placeholder analysis.
- G4 — branch still behind `origin/main`.

No critical issues. The three requested sanity checks on `1004c2b` all passed: one
`single_line` implementation with no import cycle (`utils/sql_placeholders` imports
nothing from `mcp_tools_sql`); `make_skipped_not_read_only_entry` is `ok=True, warn=True`
and the CLI checks `warn` before `ok`, so it cannot mask the exit code, which stays
single-sourced on the `read_only` row; decision 12's un-suffixed `(skipped)` row returns
before the reordered code and is untouched.

**Decisions**

- G1 — accept. Same class as round 1's C2, which Marcus ruled "fix now"; the fix is one
  branch in `basic_preflight` beside the existing `> 1` check.
- G2 — accept. One-line docs fix; two descriptions of the same status set had diverged.
- G3 — skip. The move to `utils` was correct (one implementation beats two) and
  `summary.md` rules out a new module on this branch, so there is no better home. Noted
  as a decision rather than an accident.
- G4 — rebase before the PR.

**Changes**

- `basic_preflight` returns a verdict for a zero-statement result instead of `None`.
  Covered against `count_records`, `validate_sql`, both `summarize` paths and directly,
  over all three shapes and both dialects, plus a test confirming the startup gate and
  verify row were never affected (they wrap the composition in `except SqlglotError`).
- `docs/cli.md` `[WARN]` enumeration extended with the not-read-only skip.
- `TestBasicPreflight` moved to `tests/test_basic_preflight.py` — the additions pushed
  `test_validation_tools.py` to 780 lines, over the 750 limit, and the class unit-tests a
  `utils` helper rather than `validation_tools`. Mirrors commit `4ec9a00`'s split.

`validate_where` turned out to be safe already: the predicate is embedded in a
`SELECT 1 FROM <t> WHERE <where>` probe, so a zero-statement predicate yields a
`ParseError` verdict rather than escaping. Its test asserts that shape.

**Status**: format / pylint / pytest (1113 passed, 19 skipped) / mypy / tach /
lint-imports / check_file_size all green. Committed.

## Round 4 — 2026-09-29

**Findings**: no critical, no medium. Three nits, all skipped: a docstring reflow
artifact left by an earlier edit (cosmetic, black does not reflow docstrings); the
zero-statement verdict string restated in three test modules (independent restatement
of an expected value is defensible); and this log file being untracked (handled below).

**Verdict on the `ValidationError` label**: keep it. The premise that neighbouring
verdicts derive their label from an exception class turned out to be false — only the
`except SqlglotError` catch does, and only because the class genuinely varies between
`ParseError` and `TokenError`. Five other sites use the bare literal `ValidationError`
for "this code decided to reject", including the `> 1` branch the new check sits beside.
Changing it would make the new verdict the odd one out, and there is no exception to
name. Renaming the convention repo-wide is a separate change.

**Changes**: none — zero code changes this round, so the review loop ends here.

**Status**: no changes needed.

## Final Status

Four rounds. Three produced fixes (`eb0ea0f`, `1004c2b`, `663c7e2`); round 4 produced
none, which is what ends the loop.

The thread running through all three fix rounds was one defect class: the parse contract
was not uniformly fail-closed. Round 1 found `read_only_rejection` catching only
`ParseError` while sqlglot raises a sibling `TokenError` — one unbalanced quote in a
`[queries.*]` entry killed server startup. Round 2 found the same narrow catch in
`basic_preflight`, caller-facing rather than startup-fatal. Round 3 found the remaining
hole from the other direction: SQL that tokenizes to zero statements passed the count
check and raised out of the tool. Each was the same failure mode reached by a different
trigger, and the three together now close it.

The other substantive fix was a scope call Marcus ruled on: the new
`passthrough_source_violation` guard was wired only into the `queries.*` gate, leaving
the `OPENQUERY` linked-server write hole open on `count_records` and both
`summarize_columns` gates — a surface needing no config change at all. Fixed here rather
than deferred to a follow-up issue.

Also landed: `verify` no longer EXPLAINs a query before proving it read-only (it used to
report the database's `no such table` complaint as the reason a write was bad); the
`:memory:` check covers the URI spellings; and the verify snapshot no longer asserts
byte-identity against sqlglot's own error wording.

Final checks: pylint, pytest (1113 passed, 19 skipped), mypy, tach, lint-imports
(2 contracts kept), vulture (no output), check_file_size (187 files under 750) — all
green.

Outstanding, not code: the branch is behind `origin/main` and needs a rebase before the
PR. An earlier attempt did not rebase cleanly (issue comment, 2026-09-28).
