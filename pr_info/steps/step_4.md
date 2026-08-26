# Step 4 — Default log file for `server`, console output, and logged startup failures

**Reference:** [summary.md](./summary.md) §1 "Two log sinks", §4 "Startup
failures now reach the log file" and §7 "Log-file creation failure is fatal".

## Why

MCP clients typically discard a server's stderr, so a file is the only durable
diagnostic trail. `server` gets one per launch; `init`/`verify` stay
console-only. `console_level=OUTPUT` keeps user-facing messages visible on
stderr at the same time.

The friendly-error branch is part of the same change: it currently `print()`s
to stderr, which MCP clients discard, so a failed launch would produce a log
file containing nothing about the failure. Routing it through the logger is
only meaningful once `console_level` exists to keep it visible on stderr, so
the two land together.

## WHERE

**Modified**

- `src/mcp_tools_sql/main.py`
- `tests/cli/test_main_dispatch.py`

## WHAT

### `main.py` — new imports

```python
from datetime import datetime

from mcp_tools_sql.utils.log_utils import OUTPUT, setup_logging
from mcp_tools_sql.utils.user_app_data import get_user_app_data_dir
```

`Path` is already imported. `mcp_tools_sql.main` already declares a `utils`
dependency in `tach.toml` — no boundary change needed.

### `main.py` — new pure helper

```python
def _resolve_log_file(args: argparse.Namespace, command: str) -> str | None:
    """Resolve the log-file path for `command`, or None for console-only.

    --console-only wins over an explicit --log-file. Only `server` gets a
    default file; init/verify stay console-only unless --log-file is given.

    Returns:
        Path to the log file as a string, or None when no file should be used.
    """
    if args.console_only:
        return None
    if args.log_file:
        return str(args.log_file)
    if command != "server":
        return None
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    logs_dir = get_user_app_data_dir("mcp-tools-sql") / "logs"
    return str(logs_dir / f"mcp_tools_sql_{timestamp}.log")
```

Byte-for-byte the sisters' filename scheme: per-launch timestamp, no rotation,
no cleanup, no PID.

### `main.py` — wiring

Replace the Step-3 two-line block with:

```python
    command = args.command or "server"
    log_level = _resolve_log_level(args, command)
    log_file = _resolve_log_file(args, command)
    setup_logging(log_level, log_file, console_level=OUTPUT if log_file else None)
```

**`console_level` must be conditional, not unconditional.** Upstream gates the
console sink on `if console_level is not None or not log_file:` and then applies
`console_handler.setLevel(...)` with no special case for "no file given". An
unconditional `console_level=OUTPUT` would pin the console at 25 even with no
file, silently gutting `--console-only --log-level DEBUG` — the primary way to
debug a broken launch. The parametrized integration test below guards this.

The call stays **unguarded**: an unwritable `~/.mcp-tools-sql/logs/` kills the
launch with a traceback. Deliberate (summary.md §7); do not add a `try`/`except`.

### `main.py` — `--log-file` help text

```python
        help=(
            "Path for structured JSON logs "
            "(default: mcp_tools_sql_{timestamp}.log in ~/.mcp-tools-sql/logs/)"
        ),
```

Keep `type=Path` (cosmetic drift from the sisters' `type=str`, deliberately
unchanged — `_resolve_log_file` returns `str` either way).

### `main.py` — server error branch through the logger

Before:

```python
        except (ValueError, OSError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            print("Try 'mcp-tools-sql verify' for diagnostics.", file=sys.stderr)
            if log_level == "DEBUG":
                traceback.print_exc()
            return 2
```

After:

```python
        except (ValueError, OSError) as exc:
            logger.error("%s", exc)
            logger.log(OUTPUT, "Try 'mcp-tools-sql verify' for diagnostics.")
            if log_level == "DEBUG":
                traceback.print_exc()
            return 2
```

**This is `mcp_coder`'s house pattern**: `logger.error` for the error text,
`logger.log(OUTPUT, ...)` for the follow-up hint. See `mcp_coder`
`cli/main.py:203-207`, `:233-238`, `:256-258`, `:276-277`, `:291-292` — five
instances of exactly this two-line shape.

Two consequences of using `logger.error` for the first line:

- **The error reaches the log file at every `--log-level`.** `ERROR` is 40, at
  or above every choice in `DEBUG`/`INFO`/`OUTPUT`/`WARNING`/`ERROR`, so the
  file always records why a launch failed — which is the whole point of
  summary.md §4. It also survives `--console-only --log-level ERROR`, where an
  `OUTPUT`-level record would be filtered out.
- **Drop the `"Error: "` literal.** `CleanFormatter` prefixes `LEVEL: ` for any
  record above `OUTPUT` (`mcp_coder_utils/log_utils.py:90-91`), so the console
  already renders `ERROR: <exc>`. Keeping the literal would produce
  `ERROR: Error: <exc>`. `mcp_coder` writes it the same bare way — see
  `cli/commands/commit.py:85`, `:99`, `:119` and `gh_tool.py:52`.

The hint stays at `OUTPUT` and is therefore dropped from the file at
`--log-level WARNING` and above. That is intended: it is decoration, not
diagnostic content, and `mcp_coder` treats its hints identically.

`traceback.print_exc()` stays as-is — a debug-only escape hatch that already
goes to stderr. `sys` remains in use (`sys.argv[1:]` in `main()`) and
`traceback` remains in use, so do **not** remove either import. `logger`
already exists at `main.py:17`.

Use lazy `%s` formatting (pylint `W1203` is disabled project-wide, but lazy
formatting is the surrounding idiom).

## ALGORITHM

```
if --console-only:                    -> None
elif --log-file given:                -> str(that path)
elif command != "server":             -> None
else: ts = now("%Y%m%d_%H%M%S")
      -> str(~/.mcp-tools-sql/logs/mcp_tools_sql_<ts>.log)
setup_logging(level, file, console_level = OUTPUT if file else None)
on ValueError/OSError in server: logger.error(exc); logger.log(OUTPUT, hint)
                                 traceback iff level == DEBUG; return 2
```

## DATA

`_resolve_log_file` returns `str | None`. It is **pure** — it constructs a path
and creates nothing. `setup_logging` performs the `os.makedirs` and opens the
`FileHandler`.

## Tests (TDD — write first)

Add to `tests/cli/test_main_dispatch.py`. Import `_resolve_log_file` and
`OUTPUT` (`from mcp_tools_sql.utils.log_utils import OUTPUT`).

> **argparse gotcha:** global flags must precede the subcommand.
> `["--console-only", "server"]` parses; `["server", "--console-only"]` raises
> `SystemExit` because the `server` subparser has no such flag. The existing
> tests already follow the flags-first order.

### 1. Parametrized — deterministic cases

```python
@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (["--console-only", "server"], None),
        (["--log-file", "x.log", "server"], "x.log"),
        (["--console-only", "--log-file", "x.log", "server"], None),  # console wins
        (["init", "--backend", "sqlite"], None),
        (["verify"], None),
        (["--log-file", "x.log", "verify"], "x.log"),
    ],
)
def test_resolve_log_file(argv: list[str], expected: str | None) -> None:
    args = _build_parser().parse_args(argv)
    assert _resolve_log_file(args, args.command or "server") == expected
```

### 2. Standalone — the server default path

```python
def test_resolve_log_file_server_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    args = _build_parser().parse_args(["server"])
    result = _resolve_log_file(args, "server")
    assert result is not None
    resolved = Path(result)
    assert resolved.parent == tmp_path / ".mcp-tools-sql" / "logs"
    assert resolved.name.startswith("mcp_tools_sql_")
    assert resolved.name.endswith(".log")
    assert not resolved.exists()  # helper is pure: it creates nothing
```

Kept separate from the table because it needs a home monkeypatch and prefix /
suffix matching rather than an equality check (the timestamp is not
predictable). Deliberately **not** `fnmatch` — that would add a
`from fnmatch import fnmatch` import to a module whose import list Test 4 below
relies on staying as it is.

### 3. Parametrized — `setup_logging` receives the right arguments

Covers both commands, so the non-server wiring (`log_level="OUTPUT"`, no file,
`console_level=None`) is asserted end to end and not only through the pure
resolvers. Both dispatch targets are stubbed, so one test body serves every
row regardless of which command it runs:

```python
@pytest.mark.parametrize(
    ("argv", "expect_file", "expected_console_level", "expected_log_level"),
    [
        (["server"], True, OUTPUT, "INFO"),
        (["--console-only", "server"], False, None, "INFO"),  # guards the conditional
        (["verify"], False, None, "OUTPUT"),  # non-server stays console-only
    ],
)
def test_setup_logging_arguments(
    argv: list[str],
    expect_file: bool,
    expected_console_level: int | None,
    expected_log_level: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded: dict[str, Any] = {}

    def fake_setup(
        log_level: str, log_file: str | None = None, console_level: int | None = None
    ) -> None:
        recorded.update(
            log_level=log_level, log_file=log_file, console_level=console_level
        )

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr("mcp_tools_sql.main.setup_logging", fake_setup)
    monkeypatch.setattr("mcp_tools_sql.main.run_server", lambda args: None)
    monkeypatch.setattr(verify_cmd, "run", lambda args: 0)

    assert main(argv) == 0
    assert (recorded["log_file"] is not None) is expect_file
    assert recorded["console_level"] == expected_console_level
    assert recorded["log_level"] == expected_log_level
```

`verify_cmd` is already imported at the top of `test_main_dispatch.py`.
Stubbing both `run_server` and `verify_cmd.run` keeps the body command-agnostic
— the real `verify` would otherwise touch the filesystem and return a non-zero
code. The test's own `monkeypatch.setattr` on `setup_logging` is applied after
the autouse fixture from Step 3 and therefore wins.

### 4. Migrate `test_server_friendly_error_for_bad_config_returns_2`

It currently asserts `"Error:" in captured.err`. Once the prints become log
records, stderr no longer carries them under the no-op `setup_logging` fixture
from Step 3, so the message assertions move to `caplog`.

Do **not** carry the `"Error:"` literal across: it is gone from the source, and
the `ERROR: ` prefix that replaces it on the console is a `CleanFormatter`
artefact that never appears in `caplog.records`. Assert instead on the
**record's level name** (`"ERROR"`) for the exception line and on the message
text for the hint. Checking the level name is specific enough here:
`tool_logging.py:79` is the only other `logger.error` call in `src/`, and it
cannot fire on this path — so an `ERROR` record present at all means
`logger.error("%s", exc)` ran.

**`caplog` does not capture `OUTPUT` records by default** — pytest leaves the
root logger at `WARNING` and `OUTPUT` is 25, so those records are filtered
before the capture handler and are silently missing. `caplog.set_level(OUTPUT)`
is mandatory for the hint assertion. (The `logger.error` record would be
captured either way; the hint would not.)

Keep `capsys` for the traceback assertion — `traceback.print_exc()` still
writes to stderr, so that assertion remains valid unchanged. Using both
fixtures is simpler than reworking it into `exc_info` introspection.

```python
@pytest.mark.parametrize(
    "scenario",
    ["missing_config", "missing_connection_name", "unknown_backend"],
)
def test_server_friendly_error_for_bad_config_returns_2(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
    scenario: str,
) -> None:
    """Bad configs produce exit 2 with a friendly logged hint and no traceback."""
    caplog.set_level(OUTPUT)
    argv = _build_failing_args(tmp_path, scenario)
    rc = main(argv)
    captured = capsys.readouterr()
    messages = [rec.getMessage() for rec in caplog.records]
    levels = {rec.levelname for rec in caplog.records}
    assert rc == 2
    assert "ERROR" in levels  # the exception text
    assert any("verify" in msg for msg in messages)  # the OUTPUT hint
    assert "Traceback" not in captured.err
```

`_build_failing_args` is unchanged, and the three scenarios stay. Comparing
`levelname` strings avoids adding an `import logging` to the test module, which
currently imports only `argparse`, `sqlite3`, `Path`, `Any` and `pytest`.

## Exit criteria

- All four new/migrated tests pass; no log files appear under the developer's
  home directory after a full test run.
- `test_setup_logging_runs_before_run_server` still passes unmodified.
- pylint, pytest, mypy, `tach check`, `lint-imports`, `vulture` all pass.

## LLM prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_4.md`.
>
> Implement Step 4 only, TDD-first:
> 1. Add the four tests described in the step file to
>    `tests/cli/test_main_dispatch.py` (three new, plus the migration of
>    `test_server_friendly_error_for_bad_config_returns_2` to `caplog`). Run
>    them — they should fail.
> 2. Add `_resolve_log_file(args, command) -> str | None` to
>    `src/mcp_tools_sql/main.py` with the `datetime` and
>    `get_user_app_data_dir` imports, update the `--log-file` help text, and
>    wire the call as
>    `setup_logging(log_level, log_file, console_level=OUTPUT if log_file else None)`.
> 3. Replace the two `print(..., file=sys.stderr)` calls in the server
>    `except (ValueError, OSError)` branch with `logger.error("%s", exc)` for
>    the error and `logger.log(OUTPUT, ...)` for the hint. Drop the `"Error: "`
>    literal — `CleanFormatter` supplies the `ERROR: ` prefix. Leave
>    `traceback.print_exc()` alone and do not remove the `sys` or `traceback`
>    imports; both are still used.
>
> `console_level` must be **conditional** on `log_file` — an unconditional
> `OUTPUT` breaks `--console-only --log-level DEBUG`. Leave the `setup_logging`
> call unguarded (no try/except); a failure to create the log directory is
> deliberately fatal.
>
> Use MCP tools for all file operations. Then run `run_pylint_check`,
> `run_pytest_check` with `extra_args=["-n","auto"]`, `run_mypy_check`,
> `run_tach_check`, `run_lint_imports_check` and `run_vulture_check`, and
> confirm all pass.
