# Step 3b — `--help` infrastructure (mcp_coder parity) + finalize help strings

**Reference**: [summary.md](./summary.md) — section "New `cli/` package"
**Commit**: 3b of 10
**Goal**: Bring CLI `--help` UX to parity with `mcp_coder` by **copying its help-infrastructure verbatim**: `HelpHintArgumentParser`, `WideHelpFormatter`, `--version`, unified `help` subcommand. Finalize every `help="..."` string for `init`, `verify`, and the shared top-level flags. **No reimplementation** — copy the reference code precisely.

---

## WHERE

Modify:
- `src/mcp_tools_sql/main.py` — switch to `HelpHintArgumentParser`, add `--version`, add `help` subparser, dispatch help
- `src/mcp_tools_sql/cli/commands/init.py` — finalize all `help=` strings; use `WideHelpFormatter`
- `src/mcp_tools_sql/cli/commands/verify.py` — finalize all `help=` strings; use `WideHelpFormatter`
- `src/mcp_tools_sql/cli/parsers.py` (new) — house `HelpHintArgumentParser` + `WideHelpFormatter` (mirrors `mcp_coder/cli/parsers.py`)

Optionally:
- `src/mcp_tools_sql/cli/commands/help.py` (new, if a unified help-text aggregator is wanted; otherwise rely on argparse's built-in `--help`)

Tests:
- `tests/cli/test_main_dispatch.py` — extend with help/version tests, OR
- `tests/cli/test_help.py` (new) — parity tests

---

## WHAT — Copy verbatim from `mcp_coder`

Use `mcp__workspace__read_reference_file` with `reference_name="p_coder"`:
- `src/mcp_coder/cli/parsers.py` — copy `HelpHintArgumentParser` and `WideHelpFormatter` classes verbatim
- `src/mcp_coder/cli/main.py` — mirror the `--help` / `--version` / `help`-subcommand wiring pattern in `create_parser()` and the `if not args.command or args.command == "help" or args.help:` branch in `main()`

### `HelpHintArgumentParser` (copy verbatim)

Subclass of `argparse.ArgumentParser` whose `error()` override appends:
```
Try '<prog> --help' for more information.
```
to stderr on parse failure, then exits with code 2. Subparsers automatically inherit this class.

### `WideHelpFormatter` (copy verbatim)

Subclass of `argparse.RawDescriptionHelpFormatter` with a wider `max_help_position` (32) for nicer column alignment.

### `--version` flag

Top-level argument:
```python
from mcp_tools_sql import __version__   # already exposed
parser.add_argument(
    "--version",
    action="version",
    version=f"%(prog)s {__version__}",
)
```

### Unified `help` subcommand

```python
subparsers.add_parser("help", help=argparse.SUPPRESS)
```

In `main()`, treat `args.command in (None, "help")` (and `args.help` for explicit `-h/--help`) as "print help and exit 0".

mcp_coder uses `add_help=False` on the top-level parser and adds `--help`/`-h` manually so it can route to its own help command. Mirror that pattern.

---

## WHAT — Finalize all `help=` strings

Walk every `add_parser()` and `add_argument()` call across `main.py`, `cli/commands/init.py`, `cli/commands/verify.py` and replace placeholder `help=...` text with final strings.

### Top-level (in `main.py`)

| Argument | Final `help=` |
|---|---|
| `--config` | `"Path to project query config (default: discover via mcp-tools-sql.toml or [tool.mcp-tools-sql] in pyproject.toml)"` |
| `--database-config` | `"Path to database configuration file (connections, credentials). Default: ~/.mcp-tools-sql/config.toml"` |
| `--log-level` | `"Set the logging level (default: INFO)"` |
| `--log-file` | `"Path to log file (default: stderr only)"` |
| `--console-only` | `"Disable file logging; log to stderr only"` |
| `--version` | (auto via `action="version"`) |
| `--help`/`-h` | `argparse.SUPPRESS` (mcp_coder pattern) |

### `init` subparser

| Argument | Final `help=` |
|---|---|
| (subparser) | `"Create starter mcp-tools-sql.toml and ~/.mcp-tools-sql/config.toml for a chosen backend"` |
| `--backend` | `"Database backend to scaffold for (sqlite, mssql, postgresql)"` |
| `--output` | `"Path to write the project query config (default: ./mcp-tools-sql.toml)"` |
| `--pyproject` | `"Append [tool.mcp-tools-sql] to existing pyproject.toml instead of writing a standalone file"` |

Apply `formatter_class=WideHelpFormatter` to the init subparser.

### `verify` subparser

| Argument | Final `help=` |
|---|---|
| (subparser) | `"Validate environment, configuration, dependencies, and connectivity. Exit 0 on success, 1 on any error"` |

Apply `formatter_class=WideHelpFormatter` to the verify subparser.

(`verify` has no subcommand-level flags; it consumes the top-level `--config` / `--database-config`.)

---

## HOW — Integration points

- Top-level parser switches from `argparse.ArgumentParser` to `HelpHintArgumentParser`.
- All subparsers use `formatter_class=WideHelpFormatter`.
- `init.add_subparser` and `verify.add_subparser` are called from `main._build_parser()` exactly as in step 3a — only their `help=` text and `formatter_class` change.
- The `help` subparser is registered in `main._build_parser()` directly (mirrors mcp_coder's `subparsers.add_parser("help", help=argparse.SUPPRESS)` line).

---

## ALGORITHM — main dispatch (after step 3b)

```
parser = HelpHintArgumentParser(prog="mcp-tools-sql", add_help=False, formatter_class=WideHelpFormatter)
parser.add_argument("--help", "-h", action="store_true", dest="help", help=argparse.SUPPRESS)
parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
... add top-level flags ...
subparsers = parser.add_subparsers(dest="command")
subparsers.add_parser("help", help=argparse.SUPPRESS)
init.add_subparser(subparsers)
verify.add_subparser(subparsers)
... (server stays terse) ...

args = parser.parse_args(argv or sys.argv[1:])

if not args.command or args.command == "help" or args.help:
    parser.print_help()
    return 0

dispatch as in step 3a
```

---

## DATA — Exit codes

- `0` — `--help`, `--version`, `help` subcommand, or successful command
- `2` — argparse parse error (set by `HelpHintArgumentParser.error()`)
- otherwise — propagated from subcommand `run()` (steps 4–9)

---

## Tests

Add to `tests/cli/test_main_dispatch.py` (or new `tests/cli/test_help.py`):

| Test | Asserts |
|---|---|
| `test_top_level_help_exits_0_with_usage` | `main(["--help"])` raises `SystemExit(0)`; captured stdout contains `usage: mcp-tools-sql` and lists `init` and `verify` |
| `test_init_help_exits_0` | `main(["init", "--help"])` raises `SystemExit(0)`; stdout mentions `--backend` |
| `test_verify_help_exits_0` | `main(["verify", "--help"])` raises `SystemExit(0)`; stdout mentions `verify` |
| `test_version_flag_prints_version_and_exits_0` | `main(["--version"])` raises `SystemExit(0)`; stdout matches `mcp-tools-sql <semver>` |
| `test_help_subcommand_equivalent_to_help_flag` | `main(["help"])` returns 0 and prints same usage as `main(["--help"])` |
| `test_unknown_arg_emits_help_hint_and_exits_2` | `main(["--bogus"])` raises `SystemExit(2)`; captured stderr contains `Try 'mcp-tools-sql --help' for more information.` |

Use `pytest.raises(SystemExit)` and `capsys` for these.

---

## Quality gates

All five checks green.

---

## LLM Prompt for this step

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_3b.md`. Bring `mcp-tools-sql`'s CLI `--help` UX to parity with `mcp_coder` by **copying code verbatim from the `p_coder` reference project**: read `p_coder:src/mcp_coder/cli/parsers.py` and copy `HelpHintArgumentParser` and `WideHelpFormatter` into a new `src/mcp_tools_sql/cli/parsers.py`. Read `p_coder:src/mcp_coder/cli/main.py` and mirror its `--help` / `--version` / `help`-subcommand wiring in `src/mcp_tools_sql/main.py` (top-level parser becomes `HelpHintArgumentParser` with `add_help=False`; manual `--help`/`-h` argument with `argparse.SUPPRESS`; `--version` action; `subparsers.add_parser("help", help=argparse.SUPPRESS)`; route help cases to `parser.print_help()` returning 0). Apply `formatter_class=WideHelpFormatter` to the `init` and `verify` subparsers. Finalize every `help="..."` string per the WHAT-table for top-level flags (`--config`, `--database-config`, `--log-level`, `--log-file`, `--console-only`), `init` (`--backend`, `--output`, `--pyproject`), and `verify`. Add tests (in `tests/cli/test_main_dispatch.py` or a new `tests/cli/test_help.py`) asserting that `mcp-tools-sql --help`, `mcp-tools-sql init --help`, `mcp-tools-sql verify --help`, `mcp-tools-sql --version`, and `mcp-tools-sql help` all exit 0 with expected usage lines, and that an unknown flag exits 2 with the `"Try '... --help'"` hint on stderr. Do **not** reimplement; copy. Run all quality checks and ensure they pass.
