# Implementation review log 2

Issue #43 — `summarize_columns` per-column data profiling tool.
Branch: `43-summarize-columns-per-column-data-profiling-tool`.
Continues `pr_info/implementation_review_log_1.md` (3 rounds, ended NO FINDINGS
with a rebase flag).

## Round 1 — 2026-08-05

**Findings**:
- MEDIUM `src/mcp_tools_sql/summarize/render.py:295-296` — `_other_lines` formats
  `size_min`/`size_max` with `_fmt_int` (`f"{n:,}"`, no `None` guard). On T-SQL the
  `DATALENGTH` min/max aliases are always emitted for `other` columns but return SQL
  NULL when every selected row is NULL, so the `"size_min" in s` guard does not
  protect against `None`. `TypeError` propagates and `tools.py` converts it into a
  misleading `Invalid parameters. TypeError: ...`, discarding the whole profile.
- MEDIUM `src/mcp_tools_sql/summarize/render.py:457-458` — triage `min`/`max` cells
  bypass the 60-char `_truncate` (applied only in `_render_values`). String value
  MIN/MAX surface *only* in triage, so one long text column renders untruncated and
  tabulate padding inflates all 50 triage rows. Contradicts the module docstring.
- LOW `tools.py:243` — `rec.record(rows=len(profiled), cols=1)` reads oddly vs
  `count_tools`' `rows=1, cols=1`.
- LOW `render.py:262-277` — `_boolean_lines` prints the null tally twice.

**Decisions**:
- Accept both MEDIUM findings — the first is a crash on the primary target backend,
  the second breaks the tool's own documented truncation contract. Both bounded.
- Skip `rec.record(...)`: deliberate per `Decisions.md` item 7 (without it the success
  log line reports `rows=0 cols=0`). Changing it would contradict the plan.
- Skip the duplicated boolean null tally: deliberate per the design and its docstring;
  cosmetic, and working readable code is not changed for cosmetics.

**Changes**:
- `render.py` `_other_lines`: `_fmt_int` → `_fmt_stat` for the size min/max cells
  (`_fmt_stat` already blanks `None` to the em dash and keeps thousands separators).
- `render.py` `render_triage`: min/max cells wrapped as `_truncate(_fmt_stat(...))`;
  docstring notes the cap.
- `tests/summarize/test_render.py`: `test_other_block_all_null_size_stats_render_blank`
  (all-NULL T-SQL size shape, previously raised `TypeError`) and
  `test_triage_truncates_long_value_min_max` (100-char value → 60 chars + `…`).
- Checks: pylint clean, mypy clean, 767 passed / 16 skipped.

**Status**: committed

## Round 2 — 2026-08-05

Both round-1 fixes re-verified as correct and complete (every remaining `_fmt_int`
call site audited for `None` reachability; triage `_fmt_stat`→`_truncate` order right).

**Findings**:
- MEDIUM `src/mcp_tools_sql/summarize/sql.py:195` — `validate_where` re-extracts the
  predicate via `parse_one(probe).args["where"].this`. A `where` with a top-level set
  operation (`1 = 1 UNION SELECT name FROM sqlite_master`) parses the probe root as
  `exp.Union`, which has no `"where"` arg → uncaught `KeyError('where')`. Both gates
  pass it: `basic_preflight` sees one statement with no unbound params, and
  `read_only_violation` allows `exp.Union` as a root (right for `count_records`, wrong
  here). Called at `tools.py:258`, outside the `try/except` at `tools.py:264`, so it
  escapes the MCP tool instead of returning a message. Not a leak — nothing executes.
  `INTERSECT`/`EXCEPT` were already rejected cleanly (`SetOperation` siblings).
- LOW `render.py:349` — `rem_vals` interpolated bare while `rem_rows` on the next line
  uses `_fmt_int`: `… 12345 other values, 1,234,567 rows`.
- LOW `render.py:442-443` — `total_columns` docstring contradicts `tools.py:186`
  (`len(chosen)`, i.e. the requested count when `columns=` narrows).
- LOW — `Decimal` min/max/sum lose thousands separators (T-SQL only, cosmetic).
- LOW — `rem_vals == 0` suppresses the remainder line while `rem_rows > 0`, so
  percentages need not sum to 100%.

**Decisions**:
- Accept the MEDIUM: an uncaught exception escaping the tool is inconsistent with every
  other failure mode here, and the fix is a bounded guard.
- Accept both LOW formatting/docstring items — one-line Boy Scout fixes in code just
  touched.
- Skip `Decimal` separators: cosmetic, needs a new type branch, and T-SQL ships
  unverified by design.
- Skip the `rem_vals == 0` case: no information is lost (the null tally is on the line
  above); pinning the invariant is speculative.

**Changes**:
- `sql.py` `validate_where`: re-parse into a local, guard on `isinstance(parsed,
  exp.Select)` + `args.get("where")`, return
  `Invalid SQL. ValidationError: where must be a single predicate` — the same message
  class `basic_preflight` uses, so it flows through the existing `where_error` path.
  Docstring records why.
- `render.py`: `rem_vals` now formatted with `_fmt_int`; `render_triage` docstring
  corrected to describe the actual `total_columns` contract.
- `tests/summarize/test_sql.py`: `test_validate_where_rejects_union_breakout`, asserting
  on `single predicate` so it pins the new branch rather than an earlier gate.
- `tests/summarize/test_render.py`: remainder test rescaled to 10,001 rows so the
  thousands separator on `rem_vals` is actually asserted.
- Checks: pylint, mypy, ruff clean; 768 passed / 16 skipped.

**Status**: committed

## Round 3 — 2026-08-05

All three `c096296` fixes re-verified as correct. The `validate_where` guard was
checked against legitimate awkward predicates (scalar subqueries, `IN (SELECT …
UNION SELECT …)`, `EXISTS`, leading comments, `ORDER BY`/`LIMIT`/`HAVING` tails) —
all keep an `exp.Select` root with a `where` arg, so none are rejected. The guard is
a superset of the reported bug: it also covers a probe parsing to a `Select` with no
`where` at all. Also re-audited every `_fmt_int` call site for `None` reachability
(none remain), identifier-quoting escape behaviour, predicate AST reuse across the
count/scalar/value-list queries (sqlglot copies, no reparenting), and unused `params`
keys on placeholder-free queries (safe on both backends).

**Findings**: NO FINDINGS at critical/high.
- LOW / doc `render.py:495-496` — the `total_columns` docstring fix from `c096296` was
  applied to `render_triage` but not to `render_summary`, which receives the same value
  and kept the wording the fix set out to remove.

**Decisions**:
- Accept the doc item: it is the incomplete half of a finding already accepted in
  round 2, and leaving a knowingly wrong docstring is worse than the cost of the edit.
  Docstring-only, no behaviour change.

**Changes**:
- `render.py` `render_summary` docstring: `total_columns` reworded to mirror
  `render_triage` — the count the call selected before the cap (full profilable count
  when unfiltered, requested count when `columns=` narrows).
- Checks: pylint, mypy clean; 768 passed / 16 skipped.

**Status**: committed

## Round 4 — 2026-08-05

Docstring change in `82d6bad` verified accurate against the actual contract
(`tools.py:186-187` computes `total_columns` before the cap; `render.py:507` forwards
it only on the triage branch, where it feeds `column_cap_footer` alone).

**Findings**: NO FINDINGS at critical/high.
- Informational: the wording "the requested count" is post-de-duplication
  (`tools.py:178-186` drops case-insensitive repeats), so `columns=["a","a","b"]` gives
  `total_columns == 2`. Identical wording in `render_triage` was accepted in round 2.

**Decisions**: Skip the informational item — docstring imprecision affecting only a
pathological call, and re-editing the same two docstrings a third time is churn.

**Changes**: none.

**Status**: no changes needed — loop terminates.

## Final Status

Four rounds. Three produced fixes, the fourth was clean, ending the loop.

**Commits**
- `5100893` fix(summarize): blank null size stats and truncate triage min/max
- `c096296` fix(summarize): reject non-Select where probes and format remainder value count
- `82d6bad` docs(summarize): align render_summary total_columns docstring

**Defects fixed**: two crashes that escaped as misleading errors (`_fmt_int(None)` on
all-NULL T-SQL `DATALENGTH` stats; `KeyError('where')` on a `UNION` breakout in the
`where` predicate), one contract violation (triage min/max not truncated at 60 chars),
and two rendering/doc inconsistencies.

**Deliberately not fixed**: `n` clamp note surfacing in no-value-list calls;
`rec.record(rows=len(profiled))` (per `Decisions.md` item 7); duplicated boolean null
tally; `Decimal` thousands separators (cosmetic, T-SQL ships unverified by design);
`rem_vals == 0` remainder suppression; `total_columns` de-duplication wording.

**Checks**: pylint, mypy, ruff clean; 768 passed / 16 skipped; vulture no output;
import-linter 2 contracts kept, 0 broken.

**Branch**: CI PASSED, up to date with `main`, all 7 tasks complete, label
`status-07:code-review`. No PR exists yet.
