# Step 5 — `subprocess_runner` shim + import-health test

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_5.md` exactly.
> Port `tests/test_module_imports.py` first (it fails: shim and walker missing), then
> add the shim and port `tests/_import_walker.py`. Apply only the listed adaptations.
> Run format, pylint, pytest (`-n auto`), mypy, vulture; all must pass. Produce exactly one commit.

## WHERE

- `tests/test_module_imports.py` (new — port of `mcp_coder:tests/test_module_imports.py`)
- `tests/_import_walker.py` (new — port of `mcp_coder:tests/_import_walker.py`)
- `src/mcp_tools_sql/utils/subprocess_runner.py` (new)

## WHAT

```python
# src/mcp_tools_sql/utils/subprocess_runner.py
"""Subprocess execution utilities — thin shim over mcp-coder-utils."""

from mcp_coder_utils.subprocess_runner import CommandOptions, execute_subprocess

__all__ = ["CommandOptions", "execute_subprocess"]
```

```python
# tests/_import_walker.py  (stdlib only)
SKIPPED_MODULES: frozenset[str] = frozenset({"mcp_tools_sql.__main__"})
def missing_optional_package(exc: BaseException) -> str | None: ...
def walk(package_name: str) -> dict[str, Any]: ...
def main(argv: list[str]) -> None: ...   # writes json.dumps(walk("mcp_tools_sql")) to argv[1]
```

```python
# tests/test_module_imports.py
STRICT_ENV_VAR = "MCP_TOOLS_SQL_IMPORT_TEST_STRICT"
def test_missing_optional_package(build_exc, expected) -> None: ...          # 7 params
def test_walk_records_system_exit_module(probe_pkg) -> None: ...
def test_walk_reports_failing_subpackage_once_without_walking_it(probe_pkg) -> None: ...
def test_walk_records_missing_optional_extra_as_skip(probe_pkg) -> None: ...
def test_all_mcp_tools_sql_modules_import(tmp_path: Path) -> None: ...
```

## HOW — port adaptations (nothing else changes)

`tests/_import_walker.py`:
- `SKIPPED_MODULES = frozenset({"mcp_tools_sql.__main__"})` — `__main__.py` calls `sys.exit(main())` on import.
- `main()`: `walk("mcp_coder")` → `walk("mcp_tools_sql")`; docstring likewise.

`tests/test_module_imports.py`:
- Module docstring: `mcp_coder` → `mcp_tools_sql`.
- `import mcp_coder` → `import mcp_tools_sql`.
- `from mcp_coder.utils.subprocess_runner import …` → `from mcp_tools_sql.utils.subprocess_runner import CommandOptions, execute_subprocess`.
- `STRICT_ENV_VAR = "MCP_TOOLS_SQL_IMPORT_TEST_STRICT"`.
- `test_all_mcp_coder_modules_import` → `test_all_mcp_tools_sql_modules_import`; inside it `mcp_coder.__file__` / `mcp_coder.__path__` → `mcp_tools_sql.__file__` / `mcp_tools_sql.__path__`.
- `from tests import _import_walker` / `from tests._import_walker import …` stay (`tests/__init__.py` exists).

## ALGORITHM (`walk`, as in blueprint)

```
pkg = import_module(package_name)            # root failure is not caught
for info in pkgutil.iter_modules(path, prefix) (recursive into packages):
    skip SKIPPED_MODULES; try import_module(info.name)
    except BaseException (not KeyboardInterrupt): missing extra → skips, else → failures; don't descend
return {"package_path": [...], "failures": [...], "skips": [...]}
```

`test_all_mcp_tools_sql_modules_import` runs `[sys.executable, "-P", _import_walker.__file__, report_path]` via `execute_subprocess` with `CommandOptions(timeout_seconds=120, env={"PYTHONPATH": <src parent>})` — a fresh interpreter, so conftest mocks (e.g. the fake `pyodbc` in `tests/backends/conftest.py:29`) can't mask breaks. Skips → `warnings.warn`; plus `pytest.fail` when `STRICT_ENV_VAR == "1"`.

## DATA

Walker report: `{"package_path": list[str], "failures": list[{"module","type","message"}], "skips": list[{"module","missing","message"}]}`.

## Checks

- `run_pytest_check(extra_args=["-n", "auto", "tests/test_module_imports.py", "-v"])` → all pass.
- Strict mode locally: `run_pytest_check(extra_args=["tests/test_module_imports.py"], env_vars={"MCP_TOOLS_SQL_IMPORT_TEST_STRICT": "1"})` → pass. If it fails with real import failures (not skips), write one line to `pr_info/.blocked.txt` naming the module and stop. Skips caused only by an optional backend extra not installed locally are acceptable here (CI confirms in step 6).
- `run_vulture_check` → shim names not flagged (used by the test).
- format, pylint, full pytest (`-n auto`), mypy pass. Fix mypy findings in the ported files with annotation-only changes.

## Commit

`test: add import-health walker and subprocess_runner shim`
