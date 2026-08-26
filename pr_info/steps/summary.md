# Issue #37 — Default server logging to file, with OUTPUT-level console output

## Goal

Make the `server` command write a **durable JSON log file** under
`~/.mcp-tools-sql/logs/` by default, while still emitting user-facing
messages to the **console at `OUTPUT` level**. MCP clients typically discard
a server's stderr, so today there is no way to find out what happened after a
launch. `init` and `verify` stay console-only.

`--console-only` remains the opt-in for inline stderr; `--log-file <path>`
remains the explicit override; `--console-only` wins when both are given.

## Architectural / design changes

### 1. Two log sinks with independent thresholds (new)

Until now `setup_logging` was file **XOR** console. `mcp-coder-utils@55f29d8`
added a `console_level` parameter enabling both at once:

```python
setup_logging(log_level: str | int,
              log_file: str | None = None,
              console_level: str | int | None = None) -> None
```

`mcp-tools-sql` becomes the **first consumer** of that parameter in the
ecosystem. Resulting model:

| Sink | Format | Threshold |
|------|--------|-----------|
| Log file | structured JSON | resolved `--log-level` |
| Console (stderr) | plain text (`CleanFormatter`) | `OUTPUT` (25) whenever a log file exists |

`--log-level` therefore sets the **file** threshold only. `--console-only` is
the escape hatch for detailed inline output.

### 2. Per-command logging defaults (new)

`main.py` gains two **pure** resolver functions, so the policy is testable
without filesystem side effects:

| Command | resolved `--log-level` | log file |
|---------|------------------------|----------|
| `server` | `INFO` | `~/.mcp-tools-sql/logs/mcp_tools_sql_<timestamp>.log`, one per launch |
| `init`, `verify` | `OUTPUT` | none |

An explicit `--log-level` always wins. `server` keeps `INFO` because
`tool_logging.py:81` and `server.py:131` — essentially the entire useful
content of the log file — are `INFO` records. `init`/`verify` have almost
nothing at `INFO`, so `OUTPUT` there is pure gain (clean console).

This mirrors `mcp_coder`'s `_resolve_log_level` (`cli/main.py:65-79`) and
establishes the ecosystem split: **server binary → file, subcommand CLI →
console**.

### 3. `OUTPUT` log level adopted

`OUTPUT` (25) is added to `--log-level` choices and re-exported through the
existing `utils/log_utils.py` shim. `--log-level` gains `default=None` so the
per-command resolver can distinguish "not given" from "explicitly INFO".
`CRITICAL` is deliberately **not** added (the sisters accept it; keeping the
diff minimal).

### 4. Startup failures now reach the log file

`main.py`'s friendly-error branch currently `print()`s to stderr, which MCP
clients discard — so the new log file would record nothing about a failed
launch. It moves onto the logger, split the way `mcp_coder`'s CLI splits it
(`cli/main.py:203-207` and four sibling sites):

| Line | Call | Reaches the file at |
|------|------|---------------------|
| the exception text | `logger.error("%s", exc)` | **every** `--log-level` (40 ≥ all choices) |
| the "try `verify`" hint | `logger.log(OUTPUT, ...)` | `DEBUG` / `INFO` / `OUTPUT` only |

Both reach the console, which sits at `OUTPUT` whenever a file exists. Logging
the error at `ERROR` rather than `OUTPUT` is what makes "startup failures must
reach the file" true unconditionally — an `OUTPUT`-level record would be
filtered out at `--log-level WARNING` or `ERROR`, i.e. exactly when a user has
turned verbosity *down* to see only problems. The hint dropping out at those
levels is fine: it is decoration, and `mcp_coder` treats its hints the same.

The `"Error: "` literal is dropped. `CleanFormatter` prefixes `LEVEL: ` for any
record above `OUTPUT` (`mcp_coder_utils/log_utils.py:90-91`), so the console
renders `ERROR: <exc>`; keeping the literal would give `ERROR: Error: <exc>`.
`mcp_coder` logs bare exceptions for the same reason (`commit.py:85`, `:99`,
`:119`).

### 5. New `utils/user_app_data.py` shim

A 4-line re-export of `mcp_coder_utils.user_app_data.get_user_app_data_dir`,
exactly parallel to the existing `utils/log_utils.py`. It becomes the single
answer to "where is the user directory?", used for the logs dir **and** for
the three existing hardcoded `Path.home() / ".mcp-tools-sql"` constructions.
Pure refactor — `get_user_app_data_dir(name)` returns `Path.home() / f".{name}"`.

**Consequence for `tach.toml`:** `mcp_tools_sql.cli.commands` currently
declares `depends_on = [cli, config, verification]` with **no `utils`**.
`init.py` importing the shim breaks `tach check` unless `utils` is added.
`config` and `verification` already declare it. `.importlinter` needs no
change (`utils` is the bottom layer).

### 6. Dependency tracks mcp-coder-utils `main`

`console_level` is in **no PyPI release** (newest is 0.1.5, 2026-05-06;
`console_level` landed 2026-08-17). This repo publishes to PyPI, so a bare
`mcp-coder-utils` would let `pip install mcp-tools-sql` resolve to 0.1.5 and
crash **every** command — `console_level` is passed unconditionally, even when
its value is `None`. Hence:

- `[project].dependencies` carries `mcp-coder-utils>=0.1.6.dev0`.
- All five CI install sites pre-install it from git.
- `[tool.uv.sources]` / `[tool.mcp-coder.install-from-github]` are uncommented
  for local dev.
- **Step 1 also upgrades the dev venv** to that same git `main` and verifies
  both the resolved version and the `console_level` keyword. The venv currently
  holds `0.1.5.dev4+g67c11cc76`, before `console_level`; without the upgrade
  Step 4 fails with a `TypeError` that reads like a code bug. Declaring a floor
  the environment cannot satisfy is the same change, so it belongs in the same
  step — and Step 1's exit criteria are what prove it resolves.

The `.dev0` suffix is load-bearing: setuptools-scm turns a git-main install
into `0.1.6.devN+g55f29d8`, which PEP 440 sorts **below** a plain `0.1.6`. A
`>=0.1.6` floor would reject CI's own git-installed dependency.
`tools/check_no_url_deps.py` is unaffected — it rejects URL specs, not version
constraints.

### 7. Log-file creation failure is fatal and unguarded (deliberate)

`setup_logging` is called **above** the `except (ValueError, OSError)` handler.
A read-only `$HOME` or full disk now kills the launch with a traceback. This is
a decision, not an oversight — no fallback code, and the failure stays visible
rather than silently degrading. Documented in `docs/cli.md`.

## Explicitly out of scope

Log rotation / cleanup of old timestamped files; same-second collision
suffixes; a `--project-dir` flag; converting `init`/`verify`'s `print()` calls
to `logger.log(OUTPUT, ...)`; adopting `console_level` in the sister repos; an
`upstream-mypy-check.yml` workflow; relaxing the dependency floor once 0.1.6
ships.

## Files created / modified

### Created

| Path | Purpose |
|------|---------|
| `src/mcp_tools_sql/utils/user_app_data.py` | 4-line shim re-exporting `get_user_app_data_dir` |
| `tests/utils/__init__.py` | test package marker (mirrors `src/mcp_tools_sql/utils/`) |
| `tests/utils/test_user_app_data.py` | shim re-export + call-time `Path.home()` behaviour |
| `tests/cli/conftest.py` | autouse fixture no-op'ing `main.setup_logging` |

### Modified

| Path | Change | Step |
|------|--------|------|
| `pyproject.toml` | `mcp-coder-utils>=0.1.6.dev0`; uncomment uv/github sources | 1 |
| `.github/workflows/ci.yml` | git pre-install of mcp-coder-utils at 5 install sites | 1 |
| `tools/reinstall_local.sh` / `.bat` | reorder GitHub overrides before the project install — **only if** Step 1's verification shows the floor failing to resolve | 1 |
| `tach.toml` | add `mcp_tools_sql.utils` to `cli.commands` deps | 2 |
| `src/mcp_tools_sql/cli/commands/init.py` | `_database_config_path()` uses the shim | 2 |
| `src/mcp_tools_sql/config/loader.py` | default db-config path uses the shim | 2 |
| `src/mcp_tools_sql/verification/config_files.py` | default db-config path uses the shim | 2 |
| `src/mcp_tools_sql/utils/log_utils.py` | re-export `OUTPUT` | 3 |
| `src/mcp_tools_sql/main.py` | `_resolve_log_level`, `--log-level` choices/default | 3 |
| `vulture_whitelist.py` | `_.no_op_setup_logging` — the autouse fixture is never named as a parameter, so vulture flags it at 60% | 3 |
| `src/mcp_tools_sql/main.py` | `_resolve_log_file`, `console_level` wiring, help text, error path → `logger.error` + `logger.log(OUTPUT, ...)` | 4 |
| `tests/cli/test_main_dispatch.py` | resolver tests, `setup_logging` arg checks, caplog migration | 3–4 |
| `docs/cli.md` | rewritten logging rows + new `### Logging` section | 5 |
| `README.md` | new logging subsection | 5 |
| `mcp-tools-sql.md` | fix contradictory example; why file-by-default | 5 |
| `docs/architecture/architecture.md` | §6 Logging: dual sinks, per-command defaults | 5 |

### Deliberately untouched

- `.importlinter` — `utils` is already the bottom layer.
- `main.py:59`, `init.py:139`, `loader.py:111`, `models.py:219`,
  `config_files.py:63` — `~/.mcp-tools-sql` in **prose** (help text, docstrings,
  warning messages), not path construction.
- `mcp-tools-sql.md:718`'s stale `--project-dir` — adjacent to the example
  being fixed, but a different problem.
- Centralising `~/.mcp-tools-sql/config.toml` into one helper — a real
  improvement, but scope creep past this issue.

## Steps

| # | File | Summary |
|---|------|---------|
| 1 | [step_1.md](./step_1.md) | Dependency floor + CI git install + dev venv upgrade of mcp-coder-utils |
| 2 | [step_2.md](./step_2.md) | `utils/user_app_data.py` shim; replace 3 path literals; tach |
| 3 | [step_3.md](./step_3.md) | `OUTPUT` re-export; `_resolve_log_level`; `tests/cli/conftest.py` |
| 4 | [step_4.md](./step_4.md) | `_resolve_log_file`; default server log file; `console_level`; error path onto the logger |
| 5 | [step_5.md](./step_5.md) | Docs: `cli.md`, `README.md`, `mcp-tools-sql.md`, architecture |

Each step is **one commit**: tests + implementation + all checks green
(pylint, pytest, mypy, plus `tach check`, `lint-imports`, `vulture`,
`tools/check_no_url_deps.py`, and `mcp__mcp-tools-py__run_format_code` before
committing).

## Follow-up not covered here

**Manual action for Marcus, after this PR merges — no step owns it, and no step
should.** Post a comment on issue #35 noting that `docs/mcp-clients.md` (created
by #35) should mention where to find the server log files for troubleshooting:
`~/.mcp-tools-sql/logs/mcp_tools_sql_<timestamp>.log`, one per launch.

This is issue #37's Decision 6. It is a GitHub comment on another issue, not a
commit on this branch, so it is deliberately outside the step structure — an
implementing agent must not post it.
