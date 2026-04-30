# Step 2 — Drop `connection_string`, add `driver`, fix `SQLiteBackend`

**Reference**: [summary.md](./summary.md) — section "Config-model cleanup"
**Commit**: 2 of 9
**Goal**: Remove the `connection_string` ingredient; introduce `driver` for MSSQL; make `SQLiteBackend` read `config.path`.

---

## WHERE

Modify:
- `src/mcp_tools_sql/config/models.py`
- `src/mcp_tools_sql/config/loader.py`
- `src/mcp_tools_sql/backends/sqlite.py`
- `tests/backends/test_sqlite.py` — migrate ~10 fixture usages
- `tests/config/test_loader.py` — remove `connection_string` from sensitive-key test if present
- `mcp-tools-sql.md` — § 6 auth-methods table; § 6 config discovery flag rename

---

## WHAT

### `models.py::ConnectionConfig`

```python
class ConnectionConfig(BaseModel):
    backend: str = "sqlite"
    host: str = ""
    port: int = 0
    database: str = ""
    username: str = ""
    password: str = ""
    trusted_connection: bool = False
    credential_env_var: str = ""
    driver: str = "ODBC Driver 18 for SQL Server"   # NEW (MSSQL only)
    path: str = ""                                  # SQLite file path
    # connection_string: REMOVED
```

### `loader.py::_SENSITIVE_KEYS`

```python
_SENSITIVE_KEYS = {"password", "credential_env_var"}   # connection_string removed
```

### `backends/sqlite.py::SQLiteBackend.connect`

```python
def connect(self) -> None:
    if self._connection is not None:
        return
    path = self._config.path                  # was: self._config.connection_string
    if not path:
        raise ValueError("SQLite path must not be empty.")
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    self._connection = conn
```

### `tests/backends/test_sqlite.py`

Migrate the helper:
```python
def _make_backend(path: str) -> SQLiteBackend:
    return SQLiteBackend(ConnectionConfig(backend="sqlite", path=path))
```

And the explicit `connection_string=""` test:
```python
def test_connect_empty_path(self) -> None:
    backend = SQLiteBackend(ConnectionConfig(backend="sqlite", path=""))
    with pytest.raises(ValueError, match="must not be empty"):
        backend.connect()
```

### `mcp-tools-sql.md` — § 6 changes

1. Auth-methods table (~line 392-399): **remove the "Connection string" row**.
2. Config Discovery (~line 417): rename `--user-config` to `--database-config` (companion to step 1).

---

## HOW — Integration points

- `_SENSITIVE_KEYS` is module-private; just edit the literal.
- No public API change — `connection_string` was unused in the codebase outside `SQLiteBackend.connect()` and tests.
- `driver` field is added with a sensible default; nothing currently reads it (MSSQL backend is still `NotImplementedError`), but `verify` and `init` will use it later.

---

## ALGORITHM — fixture migration

```
in tests/backends/test_sqlite.py:
    replace:  ConnectionConfig(backend="sqlite", connection_string=...)
    with:     ConnectionConfig(backend="sqlite", path=...)
verify with grep that "connection_string" no longer appears in src/ or tests/
```

---

## DATA — Field summary

`ConnectionConfig` now has 10 fields (was 11): `backend`, `host`, `port`, `database`, `username`, `password`, `trusted_connection`, `credential_env_var`, `driver` (new), `path`.

---

## Tests — Update + Add

**Update**:
- All `tests/backends/test_sqlite.py` fixtures (~10 usages) → `path=` kwarg.
- `tests/config/test_loader.py::test_credential_warning` (or equivalent) — if it tested `connection_string` as sensitive, remove that assertion. The `password` case stays.

**Add (small)**:
- One test in `tests/config/test_models.py`: `ConnectionConfig().driver == "ODBC Driver 18 for SQL Server"` (default).
- One test confirming `connection_string` no longer exists on the model: e.g. `assert not hasattr(ConnectionConfig(), "connection_string")`.

---

## Quality gates

- pylint, pytest (standard exclusion markers), mypy, tach, lint-imports all green.
- Grep check: `connection_string` should not appear in `src/` or `tests/` after this step.

---

## LLM Prompt for this step

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_2.md`. Implement step 2: remove the `connection_string` field from `ConnectionConfig`, add a new `driver` field (str, default `"ODBC Driver 18 for SQL Server"`), update `_SENSITIVE_KEYS` in `config/loader.py` to drop `connection_string`, fix `SQLiteBackend.connect()` to read `self._config.path`, migrate all `connection_string=` usages in `tests/backends/test_sqlite.py` to `path=`, and update the planning doc `mcp-tools-sql.md` § 6 to remove the "Connection string" auth-methods row and rename `--user-config` to `--database-config` in the discovery section. Add two small tests: `driver` default value, and assertion that `connection_string` no longer exists on `ConnectionConfig`. Run all quality checks (pylint, pytest with standard exclusions, mypy, tach, lint-imports) and ensure they all pass before committing.
