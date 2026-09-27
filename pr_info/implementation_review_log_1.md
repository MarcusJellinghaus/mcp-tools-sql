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
