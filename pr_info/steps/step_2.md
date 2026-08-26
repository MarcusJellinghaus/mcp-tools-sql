# Step 2 — `utils/user_app_data.py` shim and removal of hardcoded home paths

**Reference:** [summary.md](./summary.md) §5 "New `utils/user_app_data.py` shim".

## Why

Step 4 needs `~/.mcp-tools-sql/logs/`. Rather than a fourth hardcoded
`Path.home() / ".mcp-tools-sql"`, adopt the ecosystem helper
`get_user_app_data_dir` through a shim, and replace the three existing
literals with it. Pure refactor — `get_user_app_data_dir("mcp-tools-sql")`
returns exactly `Path.home() / ".mcp-tools-sql"`.

## WHERE

**Created**

- `src/mcp_tools_sql/utils/user_app_data.py`
- `tests/utils/__init__.py`
- `tests/utils/test_user_app_data.py`

**Modified**

- `src/mcp_tools_sql/cli/commands/init.py` (`_database_config_path`, ~line 226)
- `src/mcp_tools_sql/config/loader.py` (`load_database_config` default, ~line 128)
- `src/mcp_tools_sql/verification/config_files.py` (`db_path` default, ~line 68)
- `tach.toml`

## WHAT

### New module (mirror `utils/log_utils.py` exactly)

```python
"""User app data directory shim — re-exports from mcp-coder-utils."""

from mcp_coder_utils.user_app_data import get_user_app_data_dir

__all__ = ["get_user_app_data_dir"]
```

### Upstream signature (already in the installed 0.1.5 — no upgrade needed here)

```python
def get_user_app_data_dir(app_name: str) -> Path  # -> Path.home() / f".{app_name}"
```

### Three replacements

Each becomes `get_user_app_data_dir("mcp-tools-sql") / "config.toml"`:

| File | Current |
|------|---------|
| `init.py` | `return Path.home() / ".mcp-tools-sql" / "config.toml"` |
| `loader.py` | `path = Path.home() / ".mcp-tools-sql" / "config.toml"` |
| `config_files.py` | `db_path = db_config_path or Path.home() / ".mcp-tools-sql" / "config.toml"` |

> In `config_files.py` keep the `db_config_path or ...` precedence. Consider
> parenthesising for readability:
> `db_path = db_config_path or (get_user_app_data_dir("mcp-tools-sql") / "config.toml")`.

Leave `Path` imported where it is still used for type hints or other paths;
remove the import only if it becomes genuinely unused.

## HOW — integration points

- Import as `from mcp_tools_sql.utils.user_app_data import get_user_app_data_dir`.
- **`tach.toml` must be updated.** `mcp_tools_sql.cli.commands` declares
  `depends_on = [cli, config, verification]` with no `utils`; add
  `{ path = "mcp_tools_sql.utils" }`. `mcp_tools_sql.config` and
  `mcp_tools_sql.verification` already declare `utils` — no change there.
- `.importlinter` needs **no** change: `utils` is the bottom layer, reachable
  from everything.
- Vulture is satisfied by `__all__` (same as the existing `log_utils.py` shim).

## ALGORITHM

None — straight substitution.

## DATA

Return types unchanged: all three sites still yield a `pathlib.Path`.

## Tests (TDD — write first)

### `tests/utils/test_user_app_data.py` — one test function

```python
def test_get_user_app_data_dir_resolves_home_at_call_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert get_user_app_data_dir("mcp-tools-sql") == tmp_path / ".mcp-tools-sql"
```

This is the anchor for the whole test strategy: it documents that `Path.home()`
is read at **call time**, which is what makes Steps 2 and 4 testable via
`monkeypatch.setattr(Path, "home", ...)`.

### Existing coverage (no new tests needed)

- `tests/cli/test_init.py` — autouse `redirect_home_and_cwd` fixture
  (line 27) already monkeypatches `Path.home` and asserts
  `Path.home() / ".mcp-tools-sql" / "config.toml"` exists after `init`.
- `tests/config/test_loader.py` (~line 178) covers the loader default.
- `tests/verification/test_config_files.py` covers the verification default.

All three must stay green unchanged — that is the proof this is a pure refactor.

## Exit criteria

- New test passes; `test_init.py`, `test_loader.py`, `test_config_files.py`
  pass **without modification**.
- `tach check` returns `[]` (it will fail before the `tach.toml` edit — that is
  expected and is the point of the edit).
- `lint-imports`, `vulture`, pylint, pytest, mypy all pass.

## LLM prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_2.md`.
>
> Implement Step 2 only, TDD-first:
> 1. Create `tests/utils/__init__.py` and `tests/utils/test_user_app_data.py`
>    with the single test described in the step file. Run it — it should fail
>    (module does not exist yet).
> 2. Create `src/mcp_tools_sql/utils/user_app_data.py` as a 4-line re-export of
>    `get_user_app_data_dir` from `mcp_coder_utils.user_app_data`, mirroring
>    `src/mcp_tools_sql/utils/log_utils.py`.
> 3. Replace the three hardcoded `Path.home() / ".mcp-tools-sql"` path
>    constructions in `cli/commands/init.py`, `config/loader.py` and
>    `verification/config_files.py` with calls to the shim. Do **not** touch the
>    `~/.mcp-tools-sql` occurrences that are prose (help text, docstrings,
>    warning messages) in `main.py:59`, `init.py:139`, `loader.py:111`,
>    `models.py:219`, `config_files.py:63`.
> 4. Add `{ path = "mcp_tools_sql.utils" }` to the `mcp_tools_sql.cli.commands`
>    `depends_on` list in `tach.toml`.
>
> Use MCP tools for all file operations. Then run `run_pylint_check`,
> `run_pytest_check` with `extra_args=["-n","auto"]`, `run_mypy_check`,
> `run_tach_check` and `run_lint_imports_check`, plus
> `run_vulture_check`, and confirm all pass. The existing tests in
> `tests/cli/test_init.py`, `tests/config/test_loader.py` and
> `tests/verification/test_config_files.py` must pass unmodified.
