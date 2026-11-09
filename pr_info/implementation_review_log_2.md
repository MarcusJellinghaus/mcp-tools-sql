# Implementation review log 2 — issue #96

Supervisor-run review of the branch `96-export-tools-as-toolspecs-from-one-factory-for-mcp-cli-and-agent-workbench`.
Carry-over from log 1: the `mcp-coder-utils` floor (needs a release with `tool_spec`; latest tag is still 0.1.6) is held for the user and not re-litigated each round.

## Round 1 — 2026-11-09
**Findings**:
- (carry-over) `server.py` `build_tool_server`: toolset not closed if `ToolServer(toolset)` raises during FastMCP registration
- `cli/commands/tool.py:47`: CLI builds a full FastMCP server only to read `toolset.specs`
- `.importlinter:47-48`: no-`mcp` contract comment claims the CLI is `mcp`-free (it isn't; passes via indirect imports)
- `server.py:33`: `FastMCPSink` drops `read_only` (no `readOnlyHint` annotation)
- `toolset.py:59`: `@dataclass(frozen=True)` makes `hash(SqlToolset)` raise `TypeError`

**Decisions**:
- Partial-build close: accept — issue requires a failed build to close its registry
- CLI via `build_tool_server`: skip — issue explicitly specifies this path
- `.importlinter` comment: accept — misleading, trivial fix
- `readOnlyHint`: skip — out of scope; issue specifies the plain `add_tool(...)` call
- Unhashable toolset: accept — confirmed by probe; `eq=False` gives identity semantics fitting a resource owner

**Changes**:
- `build_tool_server` closes the toolset and re-raises if `ToolServer()` raises; test added
- `SqlToolset` → `@dataclass(frozen=True, eq=False)`; hashability test added
- `.importlinter` comment corrected
- Checks: pytest 1535 passed / 20 skipped; pylint, mypy, ruff, lint-imports clean

**Status**: committed

## Round 2 — 2026-11-09
**Findings**: none new. CI passed on `6ce75fa`; no rebase needed.
**Decisions**: —
**Changes**: none
**Status**: no changes needed

## Final Status
- Rounds: 2; code commit `6ce75fa` (registry close on failed server registration, hashable `SqlToolset`, `.importlinter` comment).
- vulture: clean. lint-imports: 6 contracts kept, 0 broken.
- `mcp-coder-utils` floor: requirement dropped by Marcus — stays unpinned, resolved from GitHub main via `[tool.uv.sources]`. No open findings.
