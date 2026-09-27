# review-implementation review log 1

## Round 1 — 2026-09-27
**Findings**:
I'll gather context systematically.`src/mcp_tools_sql/query_helpers.py:108` — low — `Field(ge=1)` does not validate the parameter default, so a config with `max_rows_default <= 0` publishes a self-contradictory schema (`"default": 0` with `"minimum": 1`); probe-confirmed the call is contained by the layer-2 floor, but this third entry point is neither tested nor documented.
`src/mcp_tools_sql/verification/queries.py:155` — low — adds a second `cast(int, qcfg.max_rows_hard)` to work around `max_rows_hard: int | None`, which `_default_max_rows_hard` guarantees non-None; a non-Optional accessor on `QueryConfig` would remove both this cast and the one at `query_helpers.py:144`.
`tests/verification/test_queries.py:159` — low — no test covers the new `<name>.max_rows_hard` skip row on the unresolvable-pin branch (`verification/queries.py:126`), the second of the two places that must stay in sync with the four-row contract.
`tests/test_query_tools.py:363` — low — the MCP-level rejection test covers only the configured-query path; the built-in schema tools that share `build_query_sig_params` (`schema_tools.py:123`) have no equivalent test, although the issue's "covers every built-in schema tool" claim rests on that path.
**Decisions**:
Verdict(decision='tasks', tasks=['In src/mcp_tools_sql/query_helpers.py around line 108, floor the max_rows parameter default the same way the cap helper does, so a config with max_rows_default <= 0 cannot publish a schema whose "default" violates its own "minimum": 1; add a test asserting the generated schema\'s default is >= 1 for a non-positive max_rows_default.', 'Add a test in tests/verification/test_queries.py covering the unresolvable-pin branch (src/mcp_tools_sql/verification/queries.py:126) so the <name>.max_rows_hard skip row is asserted, keeping both branches pinned to the same four-row contract.', 'Add a test alongside tests/test_query_tools.py:363 that exercises the built-in schema tools path through build_query_sig_params (src/mcp_tools_sql/schema_tools.py:123), asserting max_rows below 1 is rejected there too.'], escalate_reason=None)
**Changes**:
applied

## Round 2 — 2026-09-27
**Findings**:
I'll gather context systematically.Checks run on the branch: pytest 911 passed / 19 skipped, pylint clean, mypy clean, ruff clean, vulture clean, import-linter 2/2 contracts kept.

`src/mcp_tools_sql/query_helpers.py:183` — low — the runtime fallback `kwargs.pop("max_rows", config.max_rows_default)` is not floored while the published signature default at line 110 is, so with `max_rows_default <= 0` a direct caller who omits `max_rows` gets the note "Requested max_rows=0 is below the minimum 1; using 1." attributing a value the caller never requested; same unfloored fallback at line 337.
`src/mcp_tools_sql/query_helpers.py:179` — low — `execute_and_format`'s Returns docstring still says the note is appended only "when the requested limit exceeded the hard limit", but `_cap_max_rows` now also returns a note on the below-minimum path.
`src/mcp_tools_sql/formatting.py:30` — low — the `max(..., 1)` floor and its bare `1` literal are now duplicated in four places (`formatting.py:30`, `formatting.py:67`, `query_helpers.py:110`, `query_helpers.py:147`) with no shared named bound, unlike the sibling `VALUE_LIST_MIN`/`clamp_n` pattern in `summarize/sql.py:562`.
`tests/test_query_tools.py:71` — low — the below-minimum note is asserted only on the `_cap_max_rows` return tuple; no test asserts it reaches the rendered output through `execute_and_format` or the fan-out closure, unlike the upper clamp which has `test_max_rows_hard_clamp` asserting `"capped at 10" in text`.
**Decisions**:
Verdict(decision='tasks', tasks=['Floor the runtime fallback in src/mcp_tools_sql/query_helpers.py:183 and the matching one at line 337 so an omitted max_rows resolves to at least 1 without emitting a below-minimum note that attributes a value the caller never passed; add a test for the omitted-max_rows case with max_rows_default <= 0.', 'Update the Returns docstring of execute_and_format (src/mcp_tools_sql/query_helpers.py:179) to state that the note is also appended on the below-minimum path, not only when the requested limit exceeds the hard limit.', 'Replace the duplicated max(..., 1) bare literal at formatting.py:30, formatting.py:67, query_helpers.py:110 and query_helpers.py:147 with a single shared named minimum bound, following the VALUE_LIST_MIN/clamp_n pattern in summarize/sql.py:562.', "Add a test asserting the below-minimum note reaches rendered output end to end through execute_and_format and through the fan-out closure, mirroring test_max_rows_hard_clamp's assertion on the rendered text rather than only on the _cap_max_rows return tuple."], escalate_reason=None)
**Changes**:
applied

## Round 3 — 2026-09-27
**Findings**:
Now let's review the actual implementation diffs, excluding `pr_info/` planning files.This is consistent and correct. Everything matches the design, and all prior review findings (rounds 1 and 2) were verifiably applied. This is a solid, well-tested, scope-appropriate fix.

NO FINDINGS
**Decisions**:
Verdict(decision='dismiss', tasks=[], escalate_reason=None)
**Changes**:
rebase-needed
**Escalate reason**: rebase
