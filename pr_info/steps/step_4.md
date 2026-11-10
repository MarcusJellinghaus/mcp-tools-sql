# Step 4 — `build_toolset` fails early on dependency errors

## LLM prompt
Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_4.md`.
Write the tests first, then the code. Run `run_format_code`, pylint, pytest
(`extra_args: ["-n", "auto"]`), mypy, ruff, lint-imports and tach; all must
pass. One commit: `feat(toolset): fail early on broken connection setup`.

## WHERE
- `src/mcp_tools_sql/toolset.py`
- `tests/test_toolset.py` (mirrors `toolset.py`)

## WHAT
```python
from mcp_tools_sql.backends.connection_check import check_connections

def _raise_on_dependency_errors(db_config: DatabaseConfig) -> None:
    """Raise ValueError for the first connection failing the dependency check."""
```
## ALGORITHM
```
for row in check_connections(db_config.connections):
    if not row.ok:
        hint = f" ({row.hint})" if row.hint else ""
        raise ValueError(f"Connection {row.connection!r}: {row.key}: {row.error or row.value}{hint}")
```
`build_toolset`: call `_raise_on_dependency_errors(dbcfg)` right after
`load_database_config(...)` and before `resolve_targets` / `BackendRegistry()`.
`DatabaseConfig` goes into the existing `TYPE_CHECKING` import block.
`assemble_toolset` is unchanged (registry still closed on later failures).
`build_tool_server`, `main.py` (`server` hint) and `cli/commands/tool.py`
(`Error: …`) already catch `ValueError` — no change.

## Tests (write first) — `tests/test_toolset.py`
Add to the existing module. Write sqlite query/db configs with its `_write_configs` helper,
adding a second connection per case. Patch
`mcp_tools_sql.backends.connection_check.pyodbc_version` / `odbc_drivers`.
Monkeypatch `mcp_tools_sql.toolset.BackendRegistry` with a `MagicMock` to
assert it is never called (no connection attempt) in every error case.
- default sqlite + `prod` mssql (`host`, `database`) with `pyodbc_version`
  raising `ImportError` → `ValueError` naming `'prod'` and containing `[mssql]`.
- `pg` with `backend = "postgresql"`, `database = "x"` → `ValueError` naming `'pg'`, "unsupported backend".
- mssql with configured driver not in `odbc_drivers()` → `ValueError` naming the driver.
- explicit nonexistent `database_config` → `ValueError` naming the path.
- happy path: sqlite + mssql with probes OK still builds (no regression).

## DATA
`build_toolset` signature unchanged; new `ValueError` cases above.
