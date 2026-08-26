# Step 5 — Server startup failures must reach the log file

**Reference:** [summary.md](./summary.md) §4 "Startup failures now reach the log
file".

## Why

`main.py`'s friendly-error branch `print()`s to stderr, which MCP clients
discard. After Step 4 a failed launch would produce a log file containing
nothing about the failure. Routing those messages through
`logger.log(OUTPUT, ...)` sends them to the file **and**, via the
`console_level=OUTPUT` handler from Step 4, to stderr as before.

## WHERE

**Modified**

- `src/mcp_tools_sql/main.py` (server error branch, ~lines 115-118)
- `tests/cli/test_main_dispatch.py`
  (`test_server_friendly_error_for_bad_config_returns_2`)

## WHAT

### `main.py` — replace the two prints

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
            logger.log(OUTPUT, "Error: %s", exc)
            logger.log(OUTPUT, "Try 'mcp-tools-sql verify' for diagnostics.")
            if log_level == "DEBUG":
                traceback.print_exc()
            return 2
```

Use `%s` lazy formatting (pylint `W1203` is disabled project-wide, but lazy
formatting is the surrounding idiom). `logger` already exists at `main.py:17`;
`OUTPUT` was imported in Step 4.

`traceback.print_exc()` stays as-is — it is a debug-only escape hatch and
already goes to stderr.

### Imports

`sys` remains in use (`sys.argv[1:]` in `main()`), so do **not** remove it.
`traceback` remains in use.

## ALGORITHM

None — a two-line substitution.

## DATA

Return value unchanged: exit code `2`.

## Tests (TDD — write first)

### Migrate `test_server_friendly_error_for_bad_config_returns_2`

It currently asserts `"Error:" in captured.err`. Once the prints become log
records, stderr no longer carries them under the no-op `setup_logging` fixture
from Step 3, so the message assertions move to `caplog`.

**`caplog` does not capture `OUTPUT` records by default** — pytest leaves the
root logger at `WARNING` and `OUTPUT` is 25, so records are filtered before the
capture handler and `caplog.records` is silently empty. `caplog.set_level(OUTPUT)`
is mandatory.

Keep `capsys` for the traceback assertion — `traceback.print_exc()` still writes
to stderr, so that assertion remains valid unchanged. Using both fixtures is
simpler than reworking it into `exc_info` introspection.

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
    assert rc == 2
    assert any("Error:" in msg for msg in messages)
    assert any("verify" in msg for msg in messages)
    assert "Traceback" not in captured.err
```

`_build_failing_args` is unchanged. The three scenarios stay.

## Exit criteria

- The migrated test passes for all three scenarios.
- Every other test passes unmodified.
- pylint, pytest, mypy, `tach check`, `lint-imports`, `vulture` all pass.

## LLM prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_5.md`.
>
> Implement Step 5 only, TDD-first:
> 1. Migrate `test_server_friendly_error_for_bad_config_returns_2` in
>    `tests/cli/test_main_dispatch.py` to assert the "Error:" and "verify"
>    messages via `caplog` (with a mandatory `caplog.set_level(OUTPUT)`), while
>    keeping the existing `capsys`-based `"Traceback" not in captured.err`
>    assertion. Run it — it should fail.
> 2. In `src/mcp_tools_sql/main.py`, replace the two
>    `print(..., file=sys.stderr)` calls in the server `except (ValueError,
>    OSError)` branch with `logger.log(OUTPUT, ...)` using lazy `%s`
>    formatting. Leave `traceback.print_exc()` alone, and do not remove the
>    `sys` or `traceback` imports — both are still used.
>
> Use MCP tools for all file operations. Then run `run_pylint_check`,
> `run_pytest_check` with `extra_args=["-n","auto"]`, `run_mypy_check`,
> `run_tach_check`, `run_lint_imports_check` and `run_vulture_check`, and
> confirm all pass.
