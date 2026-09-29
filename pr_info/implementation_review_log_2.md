# review-implementation review log 2

Issue #64 — summarize_columns: apply the row-count gate uniformly and fix the
inverted `columns=` advice.

Run 2 follows run 1, which ended after round 3 with a dismiss verdict and a
rebase hand-off.

## Round 1 — 2026-09-29

**Findings**:

- `src/mcp_tools_sql/summarize/render.py:556` — low — `inconsistent_counts_note()`
  attributes the skew to one cause ("the source changed while it was being
  profiled"), but a non-deterministic `sql=` source is re-executed once per pass
  and skews its own counts with no concurrent write. The sibling
  `distinct_gate_note()` was deliberately made source-kind-neutral; this one was
  not.
- `tests/summarize/test_tools.py:411` — low — `test_no_gate_note_below_the_gate`
  asserts `"omitted" not in out`, a substring generic enough to pass or fail for
  unrelated reasons. The adjacent `distinct_gate_note() not in out` is the
  assertion carrying the meaning.
- Boolean-skew gap (`true + false > rows` with neither individually over `rows`)
  — not re-raised; dismissed in run 1 round 3 as matching the issue's enumerated
  conditions.

**Decisions**:

- Accept both findings. Each is a bounded one-line change that makes the code
  more accurate; per the knowledge base, default to better quality rather than
  escalating trivia.
- The review also confirmed all five changes the issue specifies are present and
  match the spec, and that both earlier runs' task lists are applied.

**Changes**:

- `render.py` — the skew note's cause clause is now source-kind-neutral: "the
  source did not return the same rows to every query". Docstring names both
  causes.
- `tests/summarize/test_tools.py` — weak substring assertion dropped.

Checks: pylint clean, pytest 940 passed / 19 skipped, mypy clean.

**Status**: committed

## Round 2 — 2026-09-29

**Findings**: no critical issues. Four low findings, all documentation or test
fidelity:

- `src/mcp_tools_sql/summarize/render.py:69` — `ColumnProfile`'s docstring still
  called the value-list query "deep view only"; it is now gated on the row count
  in both views. Same staleness the issue listed for `tools.py:15`, which was
  fixed — this sibling sentence was missed.
- `src/mcp_tools_sql/summarize/sql.py:552` — the value-list pass section comment
  repeated the same stale "One GROUP BY (deep view only) per profiled column".
- `src/mcp_tools_sql/summarize/render.py:93` — `value_kind`'s `"none"` entry
  enumerated its producers without the gate, which change 2 makes a new producer.
- `tests/summarize/test_render_clamp.py` — the remainder-clamp fixture declared
  `varchar` with `category="other"` while carrying `distinct=10` and
  `value_kind="top"`, a combination the pipeline never builds.

The reviewer also probed the `assert distinct is not None` added in run 1 round 2
and confirmed the invariant holds on both dialects. Not a finding.

**Decisions**: accept all four. Three are the exact class of stale comment the
issue's own change list mandated fixing, and the fourth is a one-word test
fixture correction. None expands scope.

**Changes**:

- `render.py` — docstring intro now reads "in either view, when the row gate
  allows it"; `value_kind`'s `"none"` producers now include the gate.
- `sql.py` — comment only, no code touched.
- `tests/summarize/test_render_clamp.py` — fixture category `"other"` →
  `"string"`; assertions unchanged.

Checks: pylint clean, pytest 940 passed / 19 skipped, mypy clean.

**Status**: committed

## Round 3 — 2026-09-29

**Findings**: none. The reviewer confirmed the remaining diff is clean rather
than merely free of severe defects, and verified against the issue's change list:
all five changes present and matching the spec, `_clamp0` at exactly the three
named sites, all five skew conditions implemented with the specified strictness,
the footer order as decided, and every stale doc site updated.

**Decisions**: nothing to accept — no code changed.

**Status**: no changes needed

## Final Status

Three review rounds in run 2, two of which produced changes; the third produced
none, closing the loop.

**Commits**

| SHA | Subject |
|---|---|
| `38bbc55` | `fix(summarize): make the skew note's cause source-kind-neutral` |
| `3c1f7eb` | `docs(summarize): drop the stale "deep view only" from the value-list pass` |

Every finding across both rounds was low severity and either documentation
accuracy or test fidelity. No critical issue was found in any round, and no
finding required escalation.

**Architecture checks** (run by the supervisor)

- `run_vulture_check` — no output.
- `run_lint_imports_check` — PASSED, 2 contracts kept, 0 broken (Layered
  Architecture, Forbidden external imports), 49 files and 134 dependencies
  analysed.

**Quality checks** — pylint clean, mypy clean, ruff clean, pytest 940 passed /
19 skipped, file sizes within the 750-line limit.

**Carried forward, deliberately not fixed**: boolean skew is undetected when
`true + false > rows` while neither exceeds `rows` individually. Raised three
times in run 1 and dismissed — the issue enumerates five skew conditions and this
is not among them, so fixing it would exceed the agreed scope. It is a gap in the
issue's design, not a deviation from it.
