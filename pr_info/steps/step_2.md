# Step 2 — Credential mechanism migration: `${VAR}` expansion

## Goal

Replace the single-purpose `credential_env_var` field with general-purpose
`${VAR}` expansion across all `ConnectionConfig` string fields. Add the
`encrypt` / `trust_server_certificate` TLS knobs. Update `init` templates
and `verify` to match. All-in-one commit because removing the field breaks
every site that reads it.

## WHERE

| Action | Path |
|---|---|
| Modify | `src/mcp_tools_sql/config/models.py` |
| Modify | `src/mcp_tools_sql/config/loader.py` |
| Modify | `src/mcp_tools_sql/cli/commands/init.py` |
| Modify | `src/mcp_tools_sql/cli/commands/verify.py` |
| Modify | `tests/config/test_models.py` |
| Modify | `tests/config/test_loader.py` |
| Modify | `tests/cli/test_verify.py` |

## WHAT

### `config/models.py`

```python
class ConnectionConfig(BaseModel):
    backend: str = "sqlite"
    host: str = ""
    port: int = 0
    database: str = ""
    username: str = ""
    password: str = ""
    trusted_connection: bool = False
    # credential_env_var REMOVED
    encrypt: bool = True                    # NEW
    trust_server_certificate: bool = False  # NEW
    driver: str = "ODBC Driver 18 for SQL Server"
    path: str = ""
```

### `config/loader.py`

```python
def _expand_env_vars(data: dict[str, object]) -> dict[str, object]: ...
```

- Recursively walks the dict; every string value containing `${NAME}` is
  rewritten with `os.environ[NAME]`. Unset → `ValueError("Environment "
  "variable 'NAME' referenced in config is not set")`.
- Called **only** inside `load_database_config`, before
  `DatabaseConfig.model_validate(...)`.
- `_SENSITIVE_KEYS` becomes `{"password"}` (drop `credential_env_var`).

### `cli/commands/init.py`

Replace `credential_env_var = "MSSQL_PASSWORD"` with
`password = "${MSSQL_PASSWORD}"` in `_DATABASE_CONFIG_MSSQL`.
Replace `credential_env_var = "POSTGRES_PASSWORD"` with
`password = "${POSTGRES_PASSWORD}"` in `_DATABASE_CONFIG_POSTGRESQL`.

### `cli/commands/verify.py`

Remove the entire `if connection.credential_env_var: …` branch from
`verify_connection`. The remaining `elif connection.password or
connection.trusted_connection:` branch already covers the new world: by the
time verify sees the connection, `${VAR}` has been expanded or the loader
has raised.

Drop the unused `import os` if no longer referenced (or keep — harmless).

## HOW

- Loader pseudocode below; pattern `re.compile(r"\$\{([^}]+)\}")`.
- Reuse the existing `_read_toml` helper. Expansion happens between
  `_read_toml(path)` and `DatabaseConfig.model_validate(data)`.

## ALGORITHM (`_expand_env_vars`)

```
_VAR_RE = re.compile(r"\$\{([^}]+)\}")

def _expand_env_vars(data):
    if isinstance(data, dict): return {k: _expand_env_vars(v) for k, v in data.items()}
    if isinstance(data, list): return [_expand_env_vars(v) for v in data]
    if isinstance(data, str):
        def sub(m):
            name = m.group(1)
            if name not in os.environ:
                raise ValueError(f"Environment variable '{name}' referenced in config is not set")
            return os.environ[name]
        return _VAR_RE.sub(sub, data)
    return data
```

## DATA

- `_expand_env_vars` returns the same structure shape with strings rewritten.
- `port = "${MSSQL_PORT}"` → after expansion the string `"1433"` → Pydantic
  coerces to `int` naturally (existing behaviour).

## Tests (write FIRST / update FIRST)

### `tests/config/test_models.py` — additions

```python
def test_connection_config_no_credential_env_var():
    assert not hasattr(ConnectionConfig(), "credential_env_var")

def test_connection_config_encrypt_default_true():
    assert ConnectionConfig().encrypt is True

def test_connection_config_trust_server_certificate_default_false():
    assert ConnectionConfig().trust_server_certificate is False
```

### `tests/config/test_loader.py` — new class `TestEnvVarExpansion`

```python
def test_expansion_present(monkeypatch, tmp_path):
    monkeypatch.setenv("MY_PW", "secret")
    write `[connections.default]\nbackend="mssql"\npassword="${MY_PW}"\n`
    cfg = load_database_config(path)
    assert cfg.connections["default"].password == "secret"

def test_expansion_unset_raises(monkeypatch, tmp_path):
    monkeypatch.delenv("MISSING_VAR", raising=False)
    write a config that references ${MISSING_VAR}
    with pytest.raises(ValueError, match="MISSING_VAR"):
        load_database_config(path)

def test_expansion_int_coercion(monkeypatch, tmp_path):
    monkeypatch.setenv("MY_PORT", "1433")
    write `port = "${MY_PORT}"`  (string in TOML)
    cfg = load_database_config(path)
    assert cfg.connections["default"].port == 1433  # Pydantic coerces

def test_query_config_is_not_expanded(tmp_path):
    # load_query_config does NOT call _expand_env_vars
    sql with literal "${NOPE}" loads unchanged.
```

### `tests/cli/test_verify.py` — updates

- **Delete** `test_verify_connection_credential_env_var_missing` and
  `test_verify_connection_credential_env_var_set` (lines 435–475).
- Add:

```python
def test_verify_connection_credentials_password_set():
    conn = ConnectionConfig(backend="mssql", host="h", port=1433,
                             database="d", password="resolved")
    result, _ = verify_cmd.verify_connection(conn)
    assert result["credentials"]["ok"] is True

def test_verify_connection_credentials_missing_for_mssql():
    conn = ConnectionConfig(backend="mssql", host="h", port=1433, database="d")
    result, _ = verify_cmd.verify_connection(conn)
    assert result["credentials"]["ok"] is False
```

(Close any returned backend in `finally`.)

## Checks

- `mcp__tools-py__run_pylint_check`
- `mcp__tools-py__run_mypy_check`
- `mcp__tools-py__run_pytest_check(extra_args=["-n", "auto", "-m", "not git_integration and not claude_cli_integration and not claude_api_integration and not formatter_integration and not github_integration and not langchain_integration"])`
- `./tools/format_all.sh`
- Single commit.

## LLM Prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_2.md`. Implement
> Step 2 exactly: remove `credential_env_var` from `ConnectionConfig`, add
> `encrypt` and `trust_server_certificate`, add `_expand_env_vars` to the
> loader (applied only in `load_database_config`), drop `credential_env_var`
> from `_SENSITIVE_KEYS`, update the `init` MSSQL + PostgreSQL templates,
> and remove the `credential_env_var` branch in `verify_connection`. Update
> tests first (TDD), then code. Run pylint, mypy, pytest via MCP tools per
> CLAUDE.md after every edit. End with a single commit.
