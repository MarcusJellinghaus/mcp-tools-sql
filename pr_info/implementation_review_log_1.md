# review-implementation review log 1

## Round 1 — 2026-11-09
**Findings**:
Diff reviewed; checking one import-linter contract before writing the report.pyproject.toml:25 — high — The `mcp-coder-utils>=0.1.6` floor is removed instead of being raised to a release that ships `mcp_coder_utils.tool_spec`. The issue's Dependency bullet and Decisions table require that release and pin bump before merge. `[tool.uv.sources]` only applies to uv, so a pip/PyPI install can still resolve 0.1.6. With 0.1.6, importing `mcp_tools_sql.utils.tool_spec` fails with ImportError, and every toolkit, the server and the CLI fail to import. Step 10 in pr_info/steps/step_10.md:9 overrides the issue on its own authority, after the step was reported blocked.
src/mcp_tools_sql/server.py:89 — low — `build_tool_server` builds the toolset and then calls `ToolServer(toolset)`, and `ToolServer.__init__` registers specs into FastMCP with no guard. If FastMCP construction or `add_tool` raises, the toolset's registry, including backends already resolved for `query_*`/`update_*`, is never closed: `run_server`'s `finally` is never reached, and neither is the CLI `tool` path's close. The issue requires a partial build to close its registry.
**Decisions**:
Verdict(decision='escalate', tasks=[], escalate_reason="The issue requires raising the mcp-coder-utils floor to a release that ships tool_spec, but step 10 dropped the pin after being blocked, likely because that release isn't published yet; a human must confirm the release exists or publish it before the pin can be set (separately, the low finding about closing the registry on a failed partial build in server.py:89 should then be fixed too).")
**Changes**:
escalate
**Escalate reason**: The issue requires raising the mcp-coder-utils floor to a release that ships tool_spec, but step 10 dropped the pin after being blocked, likely because that release isn't published yet; a human must confirm the release exists or publish it before the pin can be set (separately, the low finding about closing the registry on a failed partial build in server.py:89 should then be fixed too).
