# Step 1 — Move `create_backend` into `backends/registry.py` (fix R0401 cycle)

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_1.md` exactly.
> Tests first (update imports), then move the function. Run format, pylint, pytest
> (`-n auto`), mypy; all must pass. Produce exactly one commit.

## Why

With `enable = ["R0401"]` (step 2), pylint reports cyclic imports `backends.base → backends.sqlite / backends.mssql → backends.base`, caused by the function-local imports in `create_backend()` (`base.py:168-175`). `registry.py` is the only importer of `create_backend` inside `backends/`.

## WHERE

- `src/mcp_tools_sql/backends/base.py`
- `src/mcp_tools_sql/backends/registry.py`
- `tests/test_smoke.py` (lines ~53, ~62)
- `tests/verification/test_connection.py` (line 11)

## WHAT

```python
# src/mcp_tools_sql/backends/registry.py
def create_backend(config: ConnectionConfig) -> DatabaseBackend: ...
```

Signature, docstring and body unchanged — only its module changes.

## HOW

1. **Tests first:** change `from mcp_tools_sql.backends.base import create_backend` to `from mcp_tools_sql.backends.registry import create_backend` in `tests/test_smoke.py` (both function-local imports) and `tests/verification/test_connection.py`. These fail until the move.
2. Move the function with `mcp__mcp-tools-py__move_symbol(source_file="src/mcp_tools_sql/backends/base.py", symbol_names=["create_backend"], dest_file="src/mcp_tools_sql/backends/registry.py")`. Check the result:
   - The function-local imports of `SQLiteBackend` / `MSSQLBackend` stay **inside** `create_backend`.
   - `registry.py` imports: `from mcp_tools_sql.backends.base import _DIALECTS, DatabaseBackend` and `from mcp_tools_sql.config.models import ConnectionConfig, ResolvedTarget`.
   - `base.py`: `from mcp_tools_sql.config.models import ConnectionConfig` was only used by `create_backend` — remove it (ruff F401 confirms).
   - Place `create_backend` above `class BackendRegistry` in `registry.py`.
3. Update references:
   - `base.py:12` comment → `# keep in sync with the create_backend dispatch chain in backends/registry.py`
   - `base.py:32` docstring (``each runs ``create_backend`` first``) names no module — leave it.
   - `registry.py` class docstring: `:func:`~mcp_tools_sql.backends.base.create_backend`` → `:func:`create_backend``.
4. Monkeypatch targets `mcp_tools_sql.backends.registry.create_backend` (tests/backends/test_registry.py, tests/cli/test_verify.py, tests/verification/test_orchestrator.py) already point at the new home — no change.

## ALGORITHM (unchanged body)

```
if config.backend == "sqlite": lazy-import SQLiteBackend; return SQLiteBackend(config)
if config.backend in ("mssql", "pyodbc"): lazy-import MSSQLBackend; return MSSQLBackend(config)
raise ValueError(f"Unsupported backend: ... Supported: {sorted(_DIALECTS)}")
```

## DATA

Returns a `DatabaseBackend` instance; raises `ValueError` for unknown backends.

## Checks

- `mcp__mcp-workspace__search_files(pattern="backends.base import.*create_backend")` → no matches.
- `mcp__mcp-tools-py__run_pylint_check(extra_args=["--enable=R0401"])` → no `R0401`. If an `R0401` involving `backends` remains, write one line to `pr_info/.blocked.txt` and stop.
- `run_lint_imports_check`, `run_tach_check` still pass.
- format, pylint, pytest (`-n auto`), mypy pass.

## Commit

`refactor(backends): move create_backend into registry to break import cycle`
