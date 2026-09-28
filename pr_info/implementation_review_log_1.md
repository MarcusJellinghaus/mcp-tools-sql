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
