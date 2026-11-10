# Step 2 — Per-connection dependency check; DEPENDENCIES per connection; remove psycopg probe

## LLM prompt
Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_2.md`.
Write the tests first, then the code. Run `run_format_code`, pylint, pytest
(`extra_args: ["-n", "auto"]`), mypy, ruff, lint-imports, tach, vulture and
deptry; all must pass. One commit:
`feat(verify): check dependencies for every connection; drop psycopg probe`.

## WHERE
- New: `src/mcp_tools_sql/backends/connection_check.py`
- `src/mcp_tools_sql/verification/dependencies.py`
- `src/mcp_tools_sql/verification/orchestrator.py` (DEPENDENCIES call only)
- Delete: `src/mcp_tools_sql/backends/postgresql.py`
- `.importlinter`, `pyproject.toml`
- Tests: `tests/backends/test_connection_check.py` (new),
  `tests/backends/test_dependency_probes.py`, `tests/verification/test_dependencies.py`,
  `tests/cli/test_verify.py`

## WHAT
`backends/connection_check.py`:
```python
MSSQL_INSTALL_HINT = "pip install mcp-tools-sql[mssql]"
ODBC_DRIVER_HINT = ("Install Microsoft ODBC Driver 18 for SQL Server "
                    "(https://learn.microsoft.com/sql/connect/odbc/download-odbc-driver-for-sql-server)")

@dataclass(frozen=True)
class DependencyRow:
    connection: str
    key: str          # "info" | "backend" | "pyodbc" | "odbc_driver"
    ok: bool
    value: str = ""
    error: str = ""
    hint: str = ""

def check_connections(connections: Mapping[str, ConnectionConfig]) -> list[DependencyRow]: ...
```
Import `pyodbc_version`, `odbc_drivers` from `backends.mssql` at module top
(tests patch them on `connection_check`), `SUPPORTED_BACKENDS`,
`normalize_backend` from `backends.base`.

## ALGORITHM
```
probe = None                                   # pyodbc probed at most once per call
for name, cfg in connections.items():
    if cfg.backend not in SUPPORTED_BACKENDS: append backend ERR "unsupported backend 'x'; supported: ..."
    elif normalize_backend(cfg.backend) == "sqlite": append info OK "(no optional dependencies for sqlite)"
    else: probe = probe or _probe_pyodbc(); append _pyodbc_row(name, probe), _driver_row(name, cfg.driver, probe)
return rows
```
- `_probe_pyodbc()` → small `NamedTuple(version: str | None, import_error: str, drivers: list[str] | None, drivers_error: str)`;
  catches `ImportError` from `pyodbc_version()` and any exception from `odbc_drivers()` (only when import worked).
- `pyodbc` row: OK `value=version`, or ERR `value="(not installed)"`, `error=import_error`, `hint=MSSQL_INSTALL_HINT`.
- `odbc_driver` row (same texts as today's `_check_odbc_driver`, moved here):
  pyodbc missing → ERR `"(skipped)"` / `"pyodbc not available"`; drivers() raised → ERR `"(error)"`;
  configured driver installed → OK `value=driver`; not installed → ERR
  `value=f"(not found: {driver!r})"`, `error=f"configured driver {driver!r} not installed; installed: {list or '(none)'}"`,
  `hint=ODBC_DRIVER_HINT`; `driver == ""` → today's fallback (first driver containing `"SQL Server"`, else ERR `"(none found)"`).

`verification/dependencies.py` (replace the whole module body):
```python
def verify_dependencies(db_config: DatabaseConfig | None) -> dict[str, CheckResult]:
    if db_config is None or not db_config.connections:
        return {"backend": make_entry(ok=False, error="cannot determine backend without valid config")}
    return {f"{r.connection}.{r.key}": make_entry(ok=r.ok, value=r.value, error=r.error, install_hint=r.hint)
            for r in check_connections(db_config.connections)}
```
Delete `_verify_dependencies_mssql`, `_check_odbc_driver`, `_verify_dependencies_postgresql`.

`orchestrator.verify_all`: replace the `default_target` / `backend` /
`configured_driver` lines with `verify_dependencies(loaded.db_config)`.
Nothing else in `verify_all` changes.

psycopg removal:
- delete `backends/postgresql.py`;
- `.importlinter` `psycopg_isolation`: remove the `ignore_imports` key (its only
  line) and change the comment to: nothing imports psycopg until the PostgreSQL
  backend (#29) re-adds `backends/postgresql.py` together with this ignore;
- `pyproject.toml` `[tool.deptry]`: add
  `per_rule_ignores = { DEP002 = ["psycopg"] }` with a comment (declared in the
  `postgresql` / `all-backends` extras, unused until #29). Keep
  `package_module_name_map.psycopg` and the `psycopg` mypy override.

## Tests (write first)
- `test_connection_check.py` (patch `connection_check.pyodbc_version` / `odbc_drivers`):
  sqlite → one `info` OK row; `postgresql` → `backend` ERR naming it and the
  supported set; mssql without pyodbc → `pyodbc` ERR with `[mssql]` hint +
  `odbc_driver` "(skipped)"; configured driver installed → OK; not installed →
  ERR whose `error` names the configured driver and lists installed ones;
  `driver=""` fallback both ways; `pyodbc` alias gets the same rows as `mssql`;
  two mssql connections → `odbc_drivers` called once (counter).
- `test_dependencies.py` (rewrite): `None` and empty `DatabaseConfig()` → single
  `backend` row; multi-connection config → keys `default.info`, `prod.pyodbc`,
  `prod.odbc_driver`; hint mapped to `install_hint`.
- `test_dependency_probes.py`: delete the three psycopg tests (incl.
  `test_postgresql_module_imports_without_psycopg`) and now-unused imports.
- `tests/cli/test_verify.py`:
  - valid sqlite config → DEPENDENCIES shows `default.info`;
  - two sqlite connections → `default.info` and `second.info`;
  - missing / invalid db config → single `backend` row (existing test stays);
  - valid db config with an unknown query-config `connection` (update the
    existing test near line 186) → per-connection rows plus the CONFIG
    `connection_valid` ERR, no `cannot determine backend` row;
  - new text test: sqlite `default` + `[connections.pg] backend = "postgresql"`,
    `database = "x"` → DEPENDENCIES contains `pg.backend` `[ERR]` with
    "unsupported backend", exit code 1.
- `verify_snapshot.txt` must stay unchanged.

## DATA
- `check_connections` → `list[DependencyRow]`, connection order, rows per connection in key order above.
- DEPENDENCIES section keys: `<connection>.<key>`, or the single `backend` row.
