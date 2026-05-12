# Plan Review Log 1

## Round 1 — 2026-05-12

**Findings**:
- F1: ToolServer/create_server call-site enumeration before edits
- F2: _register_configured_tools snippet drops SchemaTools registration
- F3: Vague _UNSET fallback note lacks a concrete trigger
- F4: Sig builder ordering unclear when required fields follow defaults
- F5: UpdateKeyConfig key semantics ("required" flag) ambiguity
- F6: Field/key name collision behaviour not specified
- F7: Tool description sourcing (closure __doc__ vs add_tool description)
- F8: Multi-row warning test under-specified (fixture + assertion shape)
- F9: SQL injection test phrased as implementation assertion, not behaviour
- F10: Helper-location rationale missing (query_tools.py vs sibling module)
- F11: Tool-name prefix test assertion not explicit (positive + negative)
- F12: _UNSET sentinel placement rationale missing
- F13: Parallel _identifier_error helpers in update_tools.py and verify.py
- F14: (covered under user-decision set; folded into F4/F6/F13/F3)
- F15: No SQL injection test for the key-value parameter path

**Decisions**:
- F1: accept (added explicit search-files step in step_5)
- F2: accept (snippet now preserves QueryTools + SchemaTools, adds UpdateTools)
- F3: accept-via-user-decision (Trigger by specific test failures)
- F4: accept-via-user-decision (Keyword-only after key)
- F5: accept (added one-line note: key always required at SQL level)
- F6: accept-via-user-decision (Reject at registration)
- F7: accept (added one-line note on single-source description)
- F8: accept (test now specifies fixture + WARNING token + affected_rows=2)
- F9: accept (test now asserts payload literal + table-still-exists)
- F10: accept (added justification in step_1)
- F11: accept (assertion is now explicit positive + negative)
- F12: accept (added justification in step_1)
- F13: accept-via-user-decision (Shared helper module)
- F14: accept (folded into F4/F6/F13/F3 user decisions)
- F15: accept (new test_sql_injection_blocked_via_key_value added)

**User decisions**:
- Sig ordering: Keyword-only after key
- Field/key clash: Reject at registration
- Error message share: Shared helper module
- _UNSET fallback trigger: Trigger by specific test failures

**Changes**:
- step_1.md: helper-location justification, _UNSET-placement justification
- step_4.md:
  - sig builder spec: key POSITIONAL_OR_KEYWORD + fields KEYWORD_ONLY with explicit Parameter sketch
  - _UNSET fallback now triggered by named test failures (concrete criteria)
  - registration validation: field/key name-collision raises ValueError
  - new test: test_field_name_clashes_with_key_raises_at_registration
  - identifier-validation error wording moved to shared helper module (identifier_error)
  - key semantics: key always required at SQL level (one-liner)
  - description sourcing one-liner (closure __doc__ and add_tool both from cfg.description)
  - >1 affected rows test: explicit fixture + WARNING token + affected_rows=2
  - SQL injection (values) test rephrased as behavioural assertion
  - new test: test_sql_injection_blocked_via_key_value
  - tool-name prefix test assertion now explicit (positive + negative)
  - new test: test_identifier_error_message_shared
- step_5.md:
  - added explicit "search call sites first" instruction
  - snippet now preserves QueryTools + SchemaTools and adds UpdateTools
  - reworded description per finding 2
- step_6.md:
  - replaced local _identifier_error with shared identifier_error import
  - updated HOW and ALGORITHM references to call the shared helper

**Status**: changes applied, awaiting commit

## Round 2 — 2026-05-12

**Findings**:
- R2-1: Step 5 SchemaTools snippet was factually wrong (blocker)
- R2-2: identifiers.py module creation not surfaced in summary
- R2-3: clarify kwargs-only closure calls in tests
- R2-4: pin identifier_error signature
- R2-5: empty description handling
- R2-6: clarify run_server test spy mechanism

**Decisions**:
- R2-1: accept (correct factual error)
- R2-2: accept (surface new module in summary + step_4; add unit test)
- R2-3: accept (one-sentence clarification)
- R2-4: accept (pin signature)
- R2-5: accept (one-line note, no test)
- R2-6: accept (rewrite spy mechanism description)

**User decisions**: none (all straightforward)

**Changes**:
- step_4.md:
  - WHERE section now lists `src/mcp_tools_sql/identifiers.py` and
    `tests/test_identifiers.py` explicitly
  - Removed "or similar signature"; canonical signature
    `identifier_error(value: str, update_name: str) -> str` is pinned
  - Added one-line note: `cfg.description` may be empty (`""`) — passed
    through verbatim to `mcp.add_tool` and the closure's `__doc__`
  - Tests intro now states all closure calls go through FastMCP (kwargs
    only); never call positionally because field params are KEYWORD_ONLY
  - Added new `tests/test_identifiers.py` unit test stub asserting
    `identifier_error("bad name", "set_status")` contains both inputs
- step_5.md:
  - Corrected `_register_configured_tools` snippet: it registers
    `QueryTools` only today; this step adds only the conditional
    `UpdateTools` line. Removed the bogus `SchemaTools(...)` line and
    added a note that `_register_builtin_tools` (where `SchemaTools`
    lives) is unchanged
  - Rewrote `test_run_server_reads_allow_updates_from_database_config`
    description to use an `__init__` wrapper that records and delegates,
    not a `run` monkeypatch
- step_6.md:
  - Pinned canonical `identifier_error(value=..., update_name=...)` call
    shape in the ALGORITHM block so step 4 and step 6 call sites match
- summary.md:
  - Added `src/mcp_tools_sql/identifiers.py` to "Created" with a
    one-line description and surfaced `tests/test_identifiers.py`

**Status**: changes applied, awaiting commit
