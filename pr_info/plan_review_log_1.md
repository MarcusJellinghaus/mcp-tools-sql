# review-plan review log 1

## Round 1 — 2026-10-20
**Findings**:
Confirmed and finalized. Here's my report.

pr_info/steps/step_3.md:58 — high — `build_kwargs(ns)` is specified as returning `dict(vars(ns))` verbatim (also restated in the ALGORITHM block at line 79), but test 5 (line 106-108) requires `kwargs["params"] == {"id": "5", "name": "foo"}`. With `--param` wired as `action="append", type=_parse_kv` (line 32-33), `ns.params` is a `list[tuple[str, str]]`, not a dict — `dict(vars(ns))` would put that list under `kwargs["params"]`, not a dict. The DATA section (line 85-87) separately claims the list-of-tuples "is converted to `dict(...)` here," contradicting the ALGORITHM/HOW text that says `build_kwargs` does nothing beyond `dict(vars(ns))`. The spec needs an explicit `params`-specific conversion step (or a custom `Action` that accumulates a dict directly) — as written, a literal implementation fails its own test 5.
**Decisions**:
Verdict(decision='tasks', tasks=["In pr_info/steps/step_3.md, resolve the contradiction between the ALGORITHM/HOW description of build_kwargs(ns) (line ~79, stated as returning dict(vars(ns)) verbatim) and the DATA section (line ~85-87) and test 5 (line 106-108), which require kwargs['params'] to be a dict built from the list of (key, value) tuples produced by --param's append/_parse_kv action. Update the spec so build_kwargs explicitly converts ns.params (a list[tuple[str, str]]) into a dict (e.g. dict(vars(ns)) followed by kwargs['params'] = dict(ns.params), or an equivalent custom argparse Action that accumulates directly into a dict), and make the ALGORITHM/HOW text consistent with the DATA section and test 5."], escalate_reason=None)
**Changes**:
applied

## Round 2 — 2026-10-20
**Findings**:
Confirmed the `argparse.SUPPRESS` + `action="append"` combination works as the plan assumes. Cleaning up the probe.Confirmed. This is enough context to finalize the report.

## Findings

`pr_info/steps/step_1.md:44` — high — The log-line relocation described (`run_server` reads "the four values ... from `server.targets`/`server.config` ... plus the returned `qpath`") omits the `builtin_tools=%d` field. The actual log statement in `server.py:126-135` has six placeholders, including `n_builtin = len(load_default_queries()) + len(PROGRAMMATIC_BUILTIN_TOOLS)` — a value computed independently, not derivable from `server.config`/`server.targets`/`qpath`. Since `build_tool_server` returns an *unregistered* server (step_1.md:33, confirmed by step_1.md's own test 2), `n_builtin` can't come from counting tools on `server.mcp` at log time either — registration hasn't happened yet. `tests/test_server.py:329` (`test_startup_builtin_tools_counter_includes_programmatic_builtins`) and `tests/test_server.py:142` both assert on this field and are listed under step_1.md's "every existing test ... still passes unchanged" guarantee. As written, a literal implementation of the ALGORITHM block (step_1.md:62-73) either drops `builtin_tools=%d` from the format string (breaking those two tests) or requires the implementer to silently reintroduce the `load_default_queries()`/`PROGRAMMATIC_BUILTIN_TOOLS` call that the spec never mentions — the step's own accounting of "what the log line needs" is incomplete.
**Decisions**:
Verdict(decision='tasks', tasks=['In pr_info/steps/step_1.md, correct the description of what run_server needs to reconstruct the relocated log line: it must include the builtin_tools=%d field (n_builtin = len(load_default_queries()) + len(PROGRAMMATIC_BUILTIN_TOOLS)), not just the four values from server.targets/server.config plus qpath. Update the ALGORITHM block (lines ~62-73) to explicitly compute/pass this value, since it cannot be derived from server.config, server.targets, qpath, or by counting tools on the unregistered server.mcp. Verify the revised spec keeps tests/test_server.py:142 and tests/test_server.py:329 (test_startup_builtin_tools_counter_includes_programmatic_builtins) passing unchanged.'], escalate_reason=None)
**Changes**:
applied
