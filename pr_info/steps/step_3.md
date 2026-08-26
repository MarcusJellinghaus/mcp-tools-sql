# Step 3 — `OUTPUT` level and per-command `--log-level` defaults

**Reference:** [summary.md](./summary.md) §2 "Per-command logging defaults" and
§3 "`OUTPUT` log level adopted".

## Why

`--log-level` currently hardcodes `default="INFO"`, which cannot express a
per-command default. Switching to `default=None` plus a pure resolver gives
`server` a full `INFO` file trail and `init`/`verify` a clean `OUTPUT` console,
while an explicit `--log-level` always wins.

## WHERE

**Created**

- `tests/cli/conftest.py`

**Modified**

- `src/mcp_tools_sql/utils/log_utils.py`
- `src/mcp_tools_sql/main.py`
- `tests/cli/test_main_dispatch.py`
- `vulture_whitelist.py` — the `_.no_op_setup_logging` entry is **already in
  place** on this branch; keep it. The autouse fixture below is never named as a
  parameter by any test, so vulture reports
  `unused function 'no_op_setup_logging' (60% confidence)` — exactly the
  threshold the `architecture` CI job uses. (`redirect_home_and_cwd` in
  `tests/cli/test_init.py` needs no entry because several tests request it by
  name.) Do not strip the entry as noise.

## WHAT

### `utils/log_utils.py` — re-export `OUTPUT`

```python
from mcp_coder_utils.log_utils import OUTPUT, log_function_call, setup_logging

__all__ = ["OUTPUT", "log_function_call", "setup_logging"]
```

### `main.py` — new pure helper

```python
def _resolve_log_level(args: argparse.Namespace, command: str) -> str:
    """Resolve the effective log level for `command`.

    An explicit --log-level always wins. Otherwise `server` defaults to INFO
    (a full file trail) and the other commands to OUTPUT (clean console).

    Returns:
        The log level name to pass to setup_logging.
    """
    if args.log_level is not None:
        return str(args.log_level)
    return "INFO" if command == "server" else "OUTPUT"
```

### `main.py` — argparse change

```python
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "OUTPUT", "WARNING", "ERROR"],
        default=None,
        help="Set the logging level (default: INFO for server, OUTPUT for init/verify)",
    )
```

No `CRITICAL` (deliberate — see summary.md §3).

### `main.py` — reorder the dispatch block

`command` is currently computed *after* `setup_logging`. Move it above:

```python
    command = args.command or "server"
    log_level = _resolve_log_level(args, command)
    log_file = None if args.console_only else args.log_file
    setup_logging(log_level, log_file)
```

and in the server error branch use the resolved value:

```python
            if log_level == "DEBUG":
                traceback.print_exc()
```

> This is logically equivalent to the current `args.log_level == "DEBUG"`
> (`_resolve_log_level` only returns `"DEBUG"` when the flag was given), so it
> is a clarity change, not a bug fix. It needs no dedicated test.

### `tests/cli/conftest.py` — autouse fixture

```python
@pytest.fixture(autouse=True)
def no_op_setup_logging(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralise real logging setup for every test under tests/cli/."""

    def _no_op(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr("mcp_tools_sql.main.setup_logging", _no_op)
```

Rationale to put in the docstring: `main()` calls `setup_logging` before
dispatch; the upgraded upstream reconfigures structlog **unconditionally**
(the old pytest special-casing was removed in `55f29d8`), and from Step 4 the
server path resolves a real path under the developer's home directory. Four
test functions in `test_main_dispatch.py` (six invocations, one parametrized
×3) take that path. Tests that need to observe the call monkeypatch it again
themselves, which takes precedence.

`tests/cli/test_verify.py` is unaffected — it calls `verify_cmd.run(args)`
directly and asserts on `captured.out`, while logging goes to stderr.

## ALGORITHM

```
command  = args.command or "server"
level    = args.log_level if given else ("INFO" if command == "server" else "OUTPUT")
setup_logging(level, None if --console-only else args.log_file)
dispatch on command; on ValueError/OSError in server, traceback iff level == DEBUG
```

## DATA

`_resolve_log_level` returns a `str` — one of `DEBUG`, `INFO`, `OUTPUT`,
`WARNING`, `ERROR`. `args.log_level` is now `str | None`.

## Tests (TDD — write first)

Add to `tests/cli/test_main_dispatch.py`, importing `_resolve_log_level`
alongside the existing `_build_parser` / `main` imports.

**One parametrized test.** Build the Namespace with the real parser rather than
a hand-rolled factory — it reads like a CLI invocation and simultaneously
covers the new `OUTPUT` choice and `default=None`:

```python
@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        ([], "INFO"),                                   # bare -> server
        (["server"], "INFO"),
        (["init", "--backend", "sqlite"], "OUTPUT"),
        (["verify"], "OUTPUT"),
        (["--log-level", "DEBUG", "server"], "DEBUG"),  # explicit wins
        (["--log-level", "DEBUG", "verify"], "DEBUG"),
        (["--log-level", "OUTPUT", "server"], "OUTPUT"),  # new choice accepted
    ],
)
def test_resolve_log_level(argv: list[str], expected: str) -> None:
    args = _build_parser().parse_args(argv)
    assert _resolve_log_level(args, args.command or "server") == expected
```

## Exit criteria

- New parametrized test passes.
- All existing tests pass. `test_server_friendly_error_for_bad_config_returns_2`
  still asserts on `capsys` and still passes — the `print()` calls are untouched
  in this step.
- pylint, pytest, mypy, `tach check`, `lint-imports`, `vulture` all pass.

## LLM prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_3.md`.
>
> Implement Step 3 only, TDD-first:
> 1. Create `tests/cli/conftest.py` with the autouse `no_op_setup_logging`
>    fixture described in the step file.
> 2. Add the parametrized `test_resolve_log_level` to
>    `tests/cli/test_main_dispatch.py`. Run it — it should fail (helper does not
>    exist).
> 3. Re-export `OUTPUT` from `src/mcp_tools_sql/utils/log_utils.py`.
> 4. Add `_resolve_log_level(args, command) -> str` to
>    `src/mcp_tools_sql/main.py`; change `--log-level` to
>    `choices=["DEBUG","INFO","OUTPUT","WARNING","ERROR"]`, `default=None`, with
>    help text stating the per-command default; move
>    `command = args.command or "server"` above the `setup_logging` call and
>    pass the resolved level; change the traceback branch to test the resolved
>    `log_level`.
>
> Do **not** add `_resolve_log_file`, `console_level`, or any change to the
> `print()` calls in the server error branch — all three are Step 4.
>
> Use MCP tools for all file operations. Then run `run_pylint_check`,
> `run_pytest_check` with `extra_args=["-n","auto"]`, `run_mypy_check`,
> `run_tach_check`, `run_lint_imports_check` and `run_vulture_check`, and
> confirm all pass.
