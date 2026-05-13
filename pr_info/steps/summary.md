# Implementation Plan — Issue #7 MS SQL Server backend (pyodbc)

## Goal

Implement a working `MSSQLBackend` (pyodbc) for `mcp-tools-sql`, and replace the
`credential_env_var` mechanism with general-purpose `${VAR}` expansion across
all `DatabaseConfig` string fields. The MSSQL stub, the `[mssql]` extra, the
`mssql_integration` CI job, and `default_queries.toml` schema introspection
already exist — the backend needs to plug into them.

## Architectural / Design Changes

### 1. New shared placeholder helper — `utils/sql_placeholders.py`

A tokenizer-aware module (`sqlparse`-based) used by both:

- The MSSQL backend, to translate `:name` → `?` (pyodbc's native placeholder).
- `query_helpers.extract_sql_params`, which currently uses a naive regex.

Placing it in `utils/` (zero upward deps) means **no `tach.toml` /
`.importlinter` changes**. `sqlparse` is added as a **core** dependency because
PostgreSQL will need the same translation logic next.

### 2. Credential mechanism migration — `${VAR}` instead of `credential_env_var`

- `ConnectionConfig.credential_env_var` field is **removed**.
- `config.loader._expand_env_vars` is added; runs on the **raw TOML dict**
  inside `load_database_config` only (not inside `load_query_config` — SQL
  must never be subject to env-var expansion).
- Recursion walks the **entire** `DatabaseConfig` dict — every section
  including `[connections.*]` and `[security]` — not just connection rows.
- Unset `${VAR}` → `ValueError` whose message includes the missing variable
  name in `${NAME}` form (Option C from supervisor review), so the existing
  `database_config_parse` verify row surfaces it automatically.
- Confined to `DatabaseConfig`, so Pydantic still coerces
  `port = "${MSSQL_PORT}"` → `int` naturally.
- `credential_env_var` is also dropped from `_SENSITIVE_KEYS` in the loader
  (the field no longer exists, the warning would be vestigial).

### 3. ConnectionConfig gains TLS knobs

- `encrypt: bool = True`
- `trust_server_certificate: bool = False`

Both default to ODBC Driver 18's secure defaults. CI/local SQL Server
deployments without a real cert must set `trust_server_certificate=true`.

### 4. MSSQL backend follows the SQLiteBackend **contract**, not its locking model

| Aspect | SQLiteBackend | MSSQLBackend |
|---|---|---|
| Lazy `connect()` | yes | yes |
| Idempotent `close()` | yes | yes |
| Post-close `RuntimeError` | yes | yes |
| `threading.Lock` scope | one-shot connect | one-shot connect |
| Per-call cursor | no (single conn cursor) | **yes** (pyodbc cursors aren't thread-safe) |
| Autocommit | n/a | **`autocommit=True`** (avoid implicit-tx-on-SELECT) |

### 5. EXPLAIN on MSSQL uses `SET SHOWPLAN_TEXT ON` … query … `SET SHOWPLAN_TEXT OFF`

Wrapped in `try/finally` so the SHOWPLAN flag never leaks. `:name → ?`
translation happens **before** SHOWPLAN because verify passes parameterized
SQL through this path.

### 6. Connection-string builder is a separately-testable module-level function

Lives inside `backends/mssql.py` (no new module needed). Implements ODBC's
comma-port syntax, `{...}` escaping for `;` / `=` / `}`, `port == 0 → 1433`,
trusted vs. password, encrypt / trust toggles.

### 7. Verify changes

- The `credential_env_var` branch in `verify_connection` is removed; the
  loader's `${VAR}` errors already surface via the existing
  `database_config_parse` row.
- On **Linux** with `trusted_connection=true`, `klist -s` is run. No cached
  ticket → `[ERR]` (explicit Kerberos misconfig).

### 8. Errors that may leak the connection string are sanitized

`pyodbc.connect()` exceptions sometimes embed the full connection string
(including the password). The backend catches `pyodbc.Error` in `connect()`,
replaces the password value with `***`, and re-raises.

## Files Created or Modified

### Created

```
src/mcp_tools_sql/utils/sql_placeholders.py     # tokenizer-aware helpers
tests/test_sql_placeholders.py                  # unit tests for the helpers
tests/backends/test_mssql.py                    # connection-string + backend + integration tests
pr_info/steps/summary.md                        # this file
pr_info/steps/step_1.md … step_7.md             # implementation steps
```

### Modified

```
pyproject.toml                                  # add sqlparse>=0.5 to core deps
src/mcp_tools_sql/query_helpers.py              # delegate extract_sql_params
src/mcp_tools_sql/config/models.py              # remove credential_env_var; add encrypt + trust_server_certificate
src/mcp_tools_sql/config/loader.py              # _expand_env_vars; drop credential_env_var from _SENSITIVE_KEYS
src/mcp_tools_sql/cli/commands/init.py          # ${VAR} in mssql + postgresql templates
src/mcp_tools_sql/cli/commands/verify.py        # remove credential_env_var branch; add klist check
src/mcp_tools_sql/backends/mssql.py             # connection-string builder + backend implementation
tests/conftest.py                               # mssql_db fixture
tests/config/test_models.py                     # new field assertions
tests/config/test_loader.py                     # _expand_env_vars tests
tests/cli/test_verify.py                        # ${VAR} + klist tests; drop credential_env_var tests
mcp-tools-sql.md                                # docs
docs/cli.md                                     # docs
```

## Step Overview

| # | Step | One-line summary |
|---|---|---|
| 1 | Foundations | Add `sqlparse`, create `utils/sql_placeholders.py`, delegate `extract_sql_params`. |
| 2 | Credential mechanism migration | Remove `credential_env_var`, add `encrypt`/`trust_server_certificate`, add `${VAR}` expansion, update `init` templates and `verify`. |
| 3 | MSSQL connection-string builder | Pure function `_build_connection_string(config) -> str` with full unit tests. |
| 4 | MSSQL backend | Implement `MSSQLBackend` lifecycle + data methods with monkeypatched-`pyodbc` unit tests. |
| 5 | MSSQL integration tests | Add `mssql_db` fixture yielding an `MSSQLTestEnv(config, schema)` dataclass + round-trip tests behind `@pytest.mark.mssql_integration`. |
| 6 | Kerberos verify check | `klist -s` on Linux when `trusted_connection=true`; `[ERR]` if no ticket. |
| 7 | Documentation | Update `mcp-tools-sql.md` and `docs/cli.md` for `${VAR}` syntax and TLS knobs. |

Each step is **exactly one commit**: tests + implementation + all checks
(pylint, mypy, pytest, tach, lint-imports) passing.

## Compliance with CLAUDE.md

Every step must:

1. Use **MCP tools** for all file/test operations.
2. Run pylint, pytest, mypy after each edit.
3. Pytest invocation uses the recommended exclusion pattern:
   `extra_args=["-n", "auto", "-m", "not git_integration and not claude_cli_integration and not claude_api_integration and not formatter_integration and not github_integration and not langchain_integration"]`
4. Run `./tools/format_all.sh` before committing.
