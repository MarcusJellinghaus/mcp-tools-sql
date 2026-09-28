# review-implementation review log 1

## Round 1 — 2026-09-28
**Findings**:
I'll gather context first.`src/mcp_tools_sql/summarize/render.py:557` — low — the note says "some totals **below** are approximate", but it is appended after the rendered summary, so the affected totals are above it; "above" is the accurate word.
`src/mcp_tools_sql/summarize/tools.py:93` — low — `_DESCRIPTION` hardcodes `1,000,000` although `DISTINCT_GATE_ROWS` is already imported in this module; the issue's own rationale for keeping the note builder in `render.py` was to avoid exactly this drift risk.
`src/mcp_tools_sql/summarize/tools.py:516` — low — above the gate the `n`-clamp footer note still prints ("Requested n=999 exceeds the maximum 50; using 50.") although no value list is produced; previously a deep call above the gate did produce value lists, so the change makes this newly self-contradictory.
`src/mcp_tools_sql/summarize/tools.py:295` — low — boolean skew is detected only when `true` or `false` individually exceeds `rows`; the likelier case `true + false > rows` (each below `rows`) goes unreported, so the deep boolean block can print a partition summing past 100% with no footer note. Matches the issue's enumerated conditions, so noted as a gap rather than a deviation.
`tests/summarize/test_tools.py:381` — low — no test asserts the gate note is *absent* below the gate (the skew note has its negative case at `test_no_skew_note_for_a_normal_profile`, the gate note has none), and no test pins `distinct_gate_note()` ahead of `source.notes` in the footer.
**Decisions**:
Verdict(decision='tasks', tasks=['In src/mcp_tools_sql/summarize/render.py:557, change the gate note wording from "below" to "above" so it accurately refers to the totals rendered before it.', 'In src/mcp_tools_sql/summarize/tools.py:93, build the _DESCRIPTION row threshold from the already-imported DISTINCT_GATE_ROWS constant instead of the hardcoded literal 1,000,000, so the text cannot drift from the gate.', 'In src/mcp_tools_sql/summarize/tools.py:516, suppress the n-clamp footer note when the row-count gate has suppressed value lists, so the summary does not report clamping an n that produced no output.', 'Add tests in tests/summarize/test_tools.py asserting (a) the gate note is absent for a profile below DISTINCT_GATE_ROWS, and (b) distinct_gate_note() is ordered ahead of source.notes in the rendered footer.'], escalate_reason=None)
**Changes**:
applied

## Round 2 — 2026-09-28
**Findings**:
I'll gather context first.`src/mcp_tools_sql/summarize/tools.py:518` — medium — the clamp-note suppression is keyed on `include_distinct` alone, but the triage view produces no value list either (`view == "deep"` is required at line 477), so a triage call with `n=999` below the gate still prints "Requested n=999 … using 50" for output that does not exist; the comment above it states a rule the code applies only half the time.
`src/mcp_tools_sql/summarize/tools.py:295` — low — boolean skew goes undetected when `true + false > rows` while neither exceeds `rows` individually, so the deep boolean block can print a partition summing past 100% with no footer note (matches the issue's enumerated five conditions, so a gap rather than a deviation; carried from round 1).
`src/mcp_tools_sql/summarize/tools.py:482` — low — `distinct is not None` in the `value_kind` ternary can no longer be false: the branch now requires `include_distinct` and a non-`other` category, which always yields a distinct count, so the guard is dead and misleadingly implies `"sample"` can be chosen for an unmeasured distinct.
`tests/summarize/test_render_clamp.py:75` — low — no test exercises a clamped remainder line and `inconsistent_counts_note()` together end-to-end, so nothing pins the pairing the design relies on (the printed zero remainder is only meaningful beside the footer note).
**Decisions**:
Verdict(decision='tasks', tasks=['In src/mcp_tools_sql/summarize/tools.py:518, key the n-clamp note suppression on the same condition that actually produces a value list (deep view AND include_distinct AND non-other category), not on include_distinct alone, so a triage call with a clamped n no longer reports clamping for output that is never rendered; update the comment to match.', 'In src/mcp_tools_sql/summarize/tools.py:482, remove the now-dead `distinct is not None` guard in the value_kind ternary (the branch already guarantees a measured distinct) so the code no longer implies "sample" is reachable there.', 'Add an end-to-end test in tests/summarize/test_render_clamp.py covering a clamped remainder line rendered together with inconsistent_counts_note(), pinning that the zero remainder appears alongside the footer note.'], escalate_reason=None)
**Changes**:
applied

## Round 3 — 2026-09-28
**Findings**:
I'll gather context first.`src/mcp_tools_sql/summarize/tools.py:295` — low — boolean skew is missed when `true + false > rows` while neither exceeds `rows` individually, so a deep boolean block can print a partition summing past 100% with no footer note (matches the issue's five enumerated conditions; carried from rounds 1–2, no new deviation).
**Decisions**:
Verdict(decision='dismiss', tasks=[], escalate_reason=None)
**Changes**:
rebase-needed
**Escalate reason**: rebase
