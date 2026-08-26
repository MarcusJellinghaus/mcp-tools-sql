# review-implementation review log 1

## Round 1 — 2026-08-26
**Findings**:
I'll start by gathering context.`tests/cli/conftest.py:11` — high — the autouse `no_op_setup_logging` fixture replaces `main.setup_logging` for every CLI test, and `test_setup_logging_arguments` (`tests/cli/test_main_dispatch.py:272`) asserts against a locally-defined `fake_setup`, so no test ever binds the `console_level=` call to the real `mcp_coder_utils.log_utils.setup_logging`; a stale/incompatible `mcp-coder-utils` (the central risk that motivated the `>=0.1.6.dev0` floor and the five CI git-install changes) yields a fully green suite plus a server that dies on every launch with `TypeError: unexpected keyword argument 'console_level'`. A `mcp_coder_utils` reachable in this workspace still exposes the pre-`console_level` signature (no `_parse_level`, still has `_is_testing_environment`), so the mismatch is not hypothetical. Cheap guard: assert `"console_level" in inspect.signature(setup_logging).parameters`, or call the real `setup_logging` once with a `tmp_path` file.
`src/mcp_tools_sql/main.py:157` — medium — `traceback.print_exc()` still writes only to stderr, so under `--log-level DEBUG` the traceback — the most valuable startup-failure diagnostic — never reaches the log file, partially defeating Decision 8 ("startup failures must reach the file"); `logger.error("%s", exc, exc_info=True)` in the DEBUG branch would route it through both sinks.
`mcp-tools-sql.md:718` — medium — "`--console-only` … cannot be combined with `--log-file`" is factually wrong and contradicts `docs/cli.md` ("`--console-only` takes precedence over `--log-file`"), Decision 5, and `_resolve_log_file`/`test_resolve_log_file`, which accept both and silently let `--console-only` win.
**Decisions**:
Verdict(decision='tasks', tasks=['Add a real-signature guard for the upstream dependency: in the CLI tests, assert that `mcp_coder_utils.log_utils.setup_logging` actually accepts `console_level` (e.g. `assert "console_level" in inspect.signature(setup_logging).parameters`) or invoke the real `setup_logging` once with a `tmp_path` log file, so the autouse `no_op_setup_logging` fixture in tests/cli/conftest.py:11 can no longer mask a stale/incompatible `mcp-coder-utils` install.', 'In src/mcp_tools_sql/main.py:157, route the startup-failure traceback through the logging system in the DEBUG branch (e.g. `logger.error("%s", exc, exc_info=True)`) instead of relying solely on `traceback.print_exc()` to stderr, so the traceback reaches the log file per Decision 8.', 'Fix mcp-tools-sql.md:718: replace the incorrect claim that `--console-only` cannot be combined with `--log-file` with the actual behavior — `--console-only` takes precedence over `--log-file` — matching docs/cli.md, Decision 5, and `_resolve_log_file`.'], escalate_reason=None)
**Changes**:
applied

## Round 2 — 2026-08-26
**Findings**:
I'll start by gathering context — knowledge base, issue details, plan files, and the diff.`src/mcp_tools_sql/main.py:70` — low — `--log-file` help advertises the `~/.mcp-tools-sql/logs/mcp_tools_sql_{timestamp}.log` default unconditionally, but only `server` gets a default file; `init`/`verify` have none (the sibling `--log-level` help does qualify per command).
`tests/cli/test_main_dispatch.py:157` — low — the caplog migration weakened the assertion: `assert "ERROR" in levels` only checks that *some* ERROR record exists anywhere in the capture and never inspects its message, so the exception text it replaced (`"Error:" in captured.err`) is no longer covered; assert on the ERROR record's `getMessage()` instead.
`tests/cli/test_main_dispatch.py:159` — low — `assert "Traceback" not in captured.err` is now vacuous: `traceback.print_exc()` is gone and the autouse `no_op_setup_logging` fixture means no handler ever writes to stderr, so the assertion can no longer fail.
`docs/cli.md:54` — low — "A failed launch is logged at `ERROR`, so the reason it failed is in the file at every `--log-level`" holds only for the `except (ValueError, OSError)` branch at `src/mcp_tools_sql/main.py:152`; any other exception escapes `main()` and leaves the new log file with no record of the failure.
**Decisions**:
Verdict(decision='dismiss', tasks=[], escalate_reason=None)
**Changes**:
dismiss
