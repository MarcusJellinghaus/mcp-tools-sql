# Step 10 — Dependency probes in the backends

See `pr_info/steps/summary.md` for the overall design.

## Kind
Restructure. TDD: tests first.

## WHERE
- `src/mcp_tools_sql/backends/mssql.py` — `pyodbc_version()`, `odbc_drivers()`.
- New `src/mcp_tools_sql/backends/postgresql.py` — `psycopg_version()` only.
- `src/mcp_tools_sql/verification/dependencies.py` — use the probes; no driver import.
- Tests: new `tests/backends/test_dependency_probes.py`; edit `tests/verification/test_dependencies.py`.

## WHAT
```python
# backends/mssql.py
def pyodbc_version() -> str:
    """Return pyodbc's version string. Raises ImportError when pyodbc is not installed."""

def odbc_drivers() -> list[str]:
    """Return installed ODBC driver names (pyodbc.drivers()). Raises ImportError / driver errors."""

# backends/postgresql.py
"""PostgreSQL backend module; for now holds only the psycopg dependency probe."""
def psycopg_version() -> str:
    """Return psycopg's version string. Raises ImportError when psycopg is not installed."""
```

## HOW
- Each probe imports its driver **inside** the function, with the same pylint/mypy comments
  the current `dependencies.py` imports use; `backends.mssql` / `backends.postgresql` must import
  without the drivers installed.
- Probes return `str(getattr(mod, "version" | "__version__", ""))` / `list(mod.drivers())` and let
  exceptions propagate unchanged (keeps `str(ImportError)` and the `drivers()` error text identical).
- `dependencies.py`:
  - `_verify_dependencies_mssql`: `version = pyodbc_version()` in the existing try; track
    `available: bool` instead of `pyodbc_module`.
  - `_check_odbc_driver(configured_driver)` (drop the module param): `drivers = odbc_drivers()` in
    the existing broad `try`.
  - `_verify_dependencies_postgresql`: `version = psycopg_version()`.
  - Rows, install hints, matching logic untouched.
- `tach.toml`: nothing (verification already depends on backends).

## ALGORITHM
```
try:
    result["pyodbc"] = make_entry(ok=True, value=pyodbc_version()); available = True
except ImportError as exc:
    result["pyodbc"] = <same not-installed row, error=str(exc)>; available = False
result["odbc_driver"] = _check_odbc_driver(configured_driver) if available else <same skipped row>
```

## DATA
Verifier rows byte-identical (`docs/cli.md` example, `tests/verification/test_orchestrator.py`).

## Tests first
`tests/backends/test_dependency_probes.py` (owner test):
- With `monkeypatch.setitem(sys.modules, "pyodbc", fake)` (`fake.version = "5.1.0"`,
  `fake.drivers = lambda: ["ODBC Driver 18 for SQL Server"]`): `pyodbc_version() == "5.1.0"`,
  `odbc_drivers() == [...]`.
- `sys.modules["pyodbc"] = None` → `pyodbc_version()` raises `ImportError`.
- `fake.drivers` raising `RuntimeError("odbc boom")` → `odbc_drivers()` raises it unchanged.
- Same pattern for `psycopg_version()` (`__version__`).
- `import mcp_tools_sql.backends.postgresql` succeeds with `sys.modules["psycopg"] = None`.
`tests/verification/test_dependencies.py`: patch
`mcp_tools_sql.verification.dependencies.pyodbc_version` / `odbc_drivers` / `psycopg_version`
(via `monkeypatch.setattr`) instead of faking the driver modules; expected rows unchanged.

## Verification
- `search_files` for `pyodbc|psycopg` imports in `src/mcp_tools_sql/verification/` → none.
- pylint, pytest (`-n auto`), mypy, lint-imports, ruff green; format; one commit.

## Commit
`refactor(backends): dependency probes for pyodbc and psycopg`

## LLM prompt
> Read `pr_info/steps/summary.md` and `pr_info/steps/step_10.md`. Write
> `tests/backends/test_dependency_probes.py` first, then add `pyodbc_version()` and
> `odbc_drivers()` to `src/mcp_tools_sql/backends/mssql.py`, create
> `src/mcp_tools_sql/backends/postgresql.py` with `psycopg_version()`, and make
> `verification/dependencies.py` use them without importing any driver. Point
> `tests/verification/test_dependencies.py` at the probes. Rows and messages must stay
> byte-identical. Use MCP tools only. Run pylint, pytest (`-n auto`), mypy, lint-imports and
> ruff; all must pass. Format, then one commit.
