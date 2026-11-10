# Step 1 — Backend names: supported set and `pyodbc` alias

## LLM prompt
Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_1.md`.
Write the tests first, then the code. Run `run_format_code`, pylint, pytest
(`extra_args: ["-n", "auto"]`), mypy, ruff, lint-imports and tach; all must
pass. One commit: `refactor(backends): supported-backend set and pyodbc alias helper`.

## WHERE
- `src/mcp_tools_sql/backends/base.py`
- `src/mcp_tools_sql/backends/registry.py`
- `src/mcp_tools_sql/verification/connection.py`
- `src/mcp_tools_sql/verification/updates.py`
- Tests: `tests/backends/test_backend_names.py` (new), `tests/backends/test_registry.py`,
  `tests/verification/test_connection.py`, `tests/verification/test_updates.py`

## WHAT
`backends/base.py`, next to `_DIALECTS` (kept for `to_dialect`):
```python
# Backend name -> sqlglot dialect; its keys are the supported backends.
_DIALECTS: dict[str, str] = {...}  # unchanged content; drop the "keep in sync" comment
SUPPORTED_BACKENDS: frozenset[str] = frozenset(_DIALECTS)
_ALIASES: dict[str, str] = {"pyodbc": "mssql"}

def normalize_backend(name: str) -> str:
    """Map a backend alias to its canonical name (``pyodbc`` -> ``mssql``)."""
    return _ALIASES.get(name, name)
```

`backends/registry.py` `create_backend(config)`:
```
if config.backend not in SUPPORTED_BACKENDS:
    raise ValueError(f"Unsupported backend: {config.backend}. Supported: {', '.join(sorted(SUPPORTED_BACKENDS))}.")
kind = normalize_backend(config.backend)
if kind == "sqlite": lazy import SQLiteBackend; return it
if kind == "mssql": lazy import MSSQLBackend; return it
raise ValueError(f"No backend implementation for {config.backend!r}")  # set member without a branch
```
Import `SUPPORTED_BACKENDS, normalize_backend` instead of `_DIALECTS`. Keep the
lazy backend imports.

`verification/connection.py` `verify_connection`: compute
`kind = normalize_backend(connection.backend)` once and replace every
`connection.backend == "mssql"` with `kind == "mssql"` (driver, DNS, Kerberos,
conn_string rows). The `backend` row value stays the raw `connection.backend`.

`verification/updates.py` `_list_table_columns`: `normalize_backend(backend_name)`
before the `== "sqlite"` / `in ("mssql", "postgresql")` checks.

QUERIES variant keys (`read_only[pyodbc]`, `resolve_sql`) stay raw — do not touch `queries.py`.

## Tests (write first)
- `test_backend_names.py`: `SUPPORTED_BACKENDS == {"sqlite", "mssql", "pyodbc"}`;
  `normalize_backend("pyodbc") == "mssql"`; `"mssql"`, `"sqlite"`, `"postgresql"` unchanged.
- `test_registry.py`: `create_backend` with `backend="postgresql"` raises
  `ValueError` listing the supported names; `pyodbc` still yields `MSSQLBackend`;
  monkeypatch `registry.SUPPORTED_BACKENDS` to include `"oracle"` → `create_backend`
  still raises `ValueError`.
- `test_connection.py`: a `backend="pyodbc"` connection (host, database, mocked
  OK backend, `gethostbyname` patched as the existing mssql DNS tests do) gets
  `driver`, `dns_lookup` and `conn_string` rows like `mssql`.
- `test_updates.py`: `_list_table_columns(mock_backend, "pyodbc", "dbo", "t")`
  runs the `INFORMATION_SCHEMA.COLUMNS` query and returns the columns (no false
  "Table not found").

## DATA
- `SUPPORTED_BACKENDS: frozenset[str]`; `normalize_backend(str) -> str`.
- No result-shape changes.
