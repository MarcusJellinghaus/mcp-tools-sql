# Step 4 — Default log file for `server`, plus simultaneous console output

**Reference:** [summary.md](./summary.md) §1 "Two log sinks" and §7
"Log-file creation failure is fatal".

> **Hard prerequisite:** the local venv must have mcp-coder-utils from git
> `main`. The released 0.1.5 `setup_logging` has no `console_level` parameter
> and this step will fail with
> `TypeError: setup_logging() got an unexpected keyword argument 'console_level'`.

## Why

MCP clients typically discard a server's stderr, so a file is the only durable
diagnostic trail. `server` gets one per launch; `init`/`verify` stay
console-only. `console_level=OUTPUT` keeps user-facing messages visible on
stderr at the same time.

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

## ALGORITHM

```
if --console-only:                    -> None
elif --log-file given:                -> str(that path)
elif command != "server":             -> None
else: ts = now("%Y%m%d_%H%M%S")
      -> str(~/.mcp-tools-sql/logs/mcp_tools_sql_<ts>.log)
setup_logging(level, file, console_level = OUTPUT if file else None)
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
    assert fnmatch(resolved.name, "mcp_tools_sql_*.log")
    assert not resolved.exists()  # helper is pure: it creates nothing
```

Kept separate from the table because it needs a home monkeypatch and glob
matching rather than an equality check.

### 3. Parametrized — `setup_logging` receives the right arguments

```python
@pytest.mark.parametrize(
    ("argv", "expect_file", "expected_console_level"),
    [
        (["server"], True, OUTPUT),
        (["--console-only", "server"], False, None),  # guards the conditional
    ],
)
def test_server_setup_logging_arguments(
    argv: list[str],
    expect_file: bool,
    expected_console_level: int | None,
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
    monkeypatch.setattr(
        "mcp_tools_sql.main.run_server", lambda args: None
    )

    assert main(argv) == 0
    assert (recorded["log_file"] is not None) is expect_file
    assert recorded["console_level"] == expected_console_level
    assert recorded["log_level"] == "INFO"
```

The test's own `monkeypatch.setattr` on `setup_logging` is applied after the
autouse fixture from Step 3 and therefore wins.

## Exit criteria

- All three new tests pass; no log files appear under the developer's home
  directory after a full test run.
- `test_setup_logging_runs_before_run_server` and
  `test_server_friendly_error_for_bad_config_returns_2` still pass unmodified.
- pylint, pytest, mypy, `tach check`, `lint-imports`, `vulture` all pass.

## LLM prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_4.md`.
>
> Verify first that the installed `mcp_coder_utils.log_utils.setup_logging`
> accepts a `console_level` keyword. If not, stop and report it.
>
> Implement Step 4 only, TDD-first:
> 1. Add the three tests described in the step file to
>    `tests/cli/test_main_dispatch.py`. Run them — they should fail.
> 2. Add `_resolve_log_file(args, command) -> str | None` to
>    `src/mcp_tools_sql/main.py` with the `datetime` and
>    `get_user_app_data_dir` imports, update the `--log-file` help text, and
>    wire the call as
>    `setup_logging(log_level, log_file, console_level=OUTPUT if log_file else None)`.
>
> `console_level` must be **conditional** on `log_file` — an unconditional
> `OUTPUT` breaks `--console-only --log-level DEBUG`. Leave the `setup_logging`
> call unguarded (no try/except); a failure to create the log directory is
> deliberately fatal. Do not touch the `print()` calls in the error branch —
> that is Step 5.
>
> Use MCP tools for all file operations. Then run `run_pylint_check`,
> `run_pytest_check` with `extra_args=["-n","auto"]`, `run_mypy_check`,
> `run_tach_check`, `run_lint_imports_check` and `run_vulture_check`, and
> confirm all pass.
