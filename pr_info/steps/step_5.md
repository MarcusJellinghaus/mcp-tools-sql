# Step 5 — Documentation

**Reference:** [summary.md](./summary.md) — all sections.

## Why

The logging model is now command-dependent and dual-sink, and the single
`Default` column in `docs/cli.md` cannot express that. `README.md` currently has
**zero** mentions of logging. `mcp-tools-sql.md` shows a self-contradictory
example. The architecture doc's Logging bullets predate both sinks.

Documentation only — no test changes.

## WHERE

- `docs/cli.md`
- `README.md`
- `mcp-tools-sql.md`
- `docs/architecture/architecture.md`

## WHAT

### 1. `docs/cli.md` — preamble qualifier (~line 20-23)

The preamble says these flags "apply to every subcommand". Add a qualifier
noting that `--log-level` and `--log-file` **resolve differently per
subcommand**, with a pointer to the new `### Logging` section.

### 2. `docs/cli.md` — replace the three logging table rows (~lines 31-33)

```markdown
| `--log-level LEVEL` | per command (see below) | One of `DEBUG`, `INFO`, `OUTPUT`, `WARNING`, `ERROR`. |
| `--log-file PATH` | per command (see below) | Write structured JSON logs to this file instead of the default path. Ignored when `--console-only` is set. |
| `--console-only` | off | Suppress the log file; send everything to stderr instead. |
```

Note the deliberate wording change: drop the current "Append logs to this
file" — appending only matters for an explicit `--log-file`, since the default
filename is unique per launch.

### 3. `docs/cli.md` — new `### Logging` section

Place it directly below the global-flags table, above `## Commands`:

```markdown
### Logging

`mcp-tools-sql` writes to two sinks with independent thresholds:

| Sink | Format | Threshold |
|------|--------|-----------|
| Log file | structured JSON | the resolved `--log-level` |
| Console (stderr) | plain text | `OUTPUT` and above — user-facing messages, warnings, errors |

Defaults depend on the command:

| Command | `--log-level` | Log file |
|---------|---------------|----------|
| `server` | `INFO` | `~/.mcp-tools-sql/logs/mcp_tools_sql_<timestamp>.log` — a new file per launch |
| `init`, `verify` | `OUTPUT` | none — console only |

`server` defaults to a file because MCP clients typically discard the server's
stderr, making the file the only durable record. A failed launch is logged at
`ERROR`, so the reason it failed is in the file at every `--log-level`. Log
files are never rotated or deleted, and the server will fail to start if
`~/.mcp-tools-sql/logs/` cannot be created.

`--log-level` sets the **file** threshold. The console stays at `OUTPUT`
whenever a log file is in use. To get detailed output inline, use
`--console-only`: it suppresses the file and sends everything at the resolved
`--log-level` to stderr. `--console-only` takes precedence over `--log-file`.
```

Use this draft as-is. It deliberately covers the "fail to start" behaviour so
it is not later "fixed" as an oversight, and the last paragraph is the single
rule that also explains why `--log-level ERROR` can make the console *more*
verbose than the file (console at 25, file at 40).

The `ERROR` sentence is load-bearing given Step 4's split: the exception text
goes through `logger.error` and so survives every threshold, while the
"Try 'mcp-tools-sql verify'" hint sits at `OUTPUT` and drops out of the file at
`--log-level WARNING` and above. Do not promise the hint here.

### 4. `README.md` — new logging subsection

Insert between `## Quick Start` (ends ~line 60) and `## Configuration`
(line 62). Keep it **short** — cover the default location, `--console-only` and
`--log-file`, then link to `docs/cli.md` rather than restating the tables:

````markdown
## Logging

The MCP server writes structured JSON logs to a new
`~/.mcp-tools-sql/logs/mcp_tools_sql_<timestamp>.log` file on every launch —
MCP clients usually discard a server's stderr, so the file is the only durable
record. User-facing messages, warnings and errors still appear on the console.

```bash
mcp-tools-sql --log-file /var/log/mcp-tools-sql.log   # explicit file
mcp-tools-sql --console-only --log-level DEBUG        # no file, verbose stderr
```

`init` and `verify` log to the console only. See [docs/cli.md](docs/cli.md#logging)
for thresholds and per-command defaults.
````

### 5. `mcp-tools-sql.md` — fix the contradictory example (~lines 706-712)

The example passes `--log-file` **and** `--console-only`, which cannot both
apply. Drop `--console-only`, and use an **absolute** path — relative
`--log-file` paths resolve against the client's working directory, which is
unpredictable:

```
mcp-tools-sql \
    --config mcp-tools-sql.toml \
    --log-level DEBUG \
    --log-file /var/log/mcp-tools-sql/server.log
```

Add a brief note below on **why** file-by-default, linking to issue #37 and
naming `mcp-workspace` / `mcp-tools-py` as prior art for the filename scheme.

> Leave the stale `--project-dir` references alone — there are **two**, at
> ~line 718 and again at ~line 852 inside an MCP-client config JSON example.
> Both are adjacent to what this step touches, both are wrong (this repo has no
> `--project-dir` flag; #35 rejected adding one), and both are a different
> problem than logging. Out of scope here — worth a follow-up issue rather than
> a silent fix inside a logging PR.

### 6. `docs/architecture/architecture.md` — §6 Cross-cutting Concerns → Logging

Replace the two existing bullets with a short block covering the new design:

- stdlib `logging` with structlog JSON backend (via mcp-coder-utils)
- `@log_function_call` decorator for timing and parameter capture
- **Two sinks with independent thresholds**: a JSON file at the resolved
  `--log-level`, plus a plain-text stderr console at `OUTPUT`
- **Per-command defaults**: `server` → `INFO` + a per-launch file under
  `~/.mcp-tools-sql/logs/`; `init`/`verify` → `OUTPUT`, console only.
  Resolved by the pure helpers `_resolve_log_level` / `_resolve_log_file` in
  `main.py`
- `--console-only` suppresses the file and takes precedence over `--log-file`
- Server startup failures go through `logger.error` (always recorded) plus an
  `OUTPUT`-level hint, following `mcp_coder`'s CLI convention
- Paths under the user home come from `utils/user_app_data.py`

Also update the `main.py` row in the §4 "Key Modules" table if its wording
("CLI: argparse, logging, subcommands") no longer reads accurately.

## ALGORITHM / DATA

None — documentation only.

## Exit criteria

- All four files updated; markdown tables render (no broken pipes).
- The `docs/cli.md` anchor `#logging` referenced from `README.md` exists.
- pylint, pytest, mypy still pass (nothing executable changed).
- `mcp__mcp-workspace__check_file_size` still passes (default `max_lines=750`).

## LLM prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_5.md`.
>
> Implement Step 5 only — documentation, no code:
> 1. `docs/cli.md`: qualify the global-flags preamble, replace the three
>    logging rows in the table, and add the `### Logging` section below the
>    table using the draft wording in the step file verbatim.
> 2. `README.md`: add a short `## Logging` section between Quick Start and
>    Configuration, linking to `docs/cli.md#logging` rather than restating the
>    tables.
> 3. `mcp-tools-sql.md`: fix the server example that passes both `--log-file`
>    and `--console-only` (drop `--console-only`, use an absolute path) and add
>    a brief note on why file-by-default, referencing issue #37 and the
>    mcp-workspace / mcp-tools-py prior art. Leave both stale `--project-dir`
>    lines (~718 and ~852) alone.
> 4. `docs/architecture/architecture.md`: update the §6 Logging bullets for the
>    dual-sink model and per-command defaults.
>
> Use MCP tools for all file operations. Then run `run_pylint_check`,
> `run_pytest_check` with `extra_args=["-n","auto"]` and `run_mypy_check` to
> confirm nothing regressed.
