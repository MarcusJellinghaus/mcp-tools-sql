# Implementation Summary — Issue #9: CLI `init` and `verify` commands

**Status**: Planning
**Issue**: #9 (M1 + M2 + config-model cleanup, single PR)
**Date**: 2026-04-30

---

## Goals

Implement two CLI subcommands and the small config-model cleanup they depend on:

1. `mcp-tools-sql init` — generate starter `mcp-tools-sql.toml` (and `~/.mcp-tools-sql/config.toml`) for a chosen backend.
2. `mcp-tools-sql verify` — validate the full setup (env, config, deps, builtin, connection, queries, updates) and exit 0/1.
3. **Config-model cleanup** (in-scope per issue): drop `connection_string`, add `driver`, rename `UserConfig` → `DatabaseConfig`, rename CLI flag `--user-config` → `--database-config`, fix `SQLiteBackend.connect()` to use `config.path`.

All in a single PR — the cleanup is tightly coupled to what `init` writes and what `verify` reads.

---

## Architectural / Design Changes

### 1. New `cli/` package

```
src/mcp_tools_sql/
└── cli/
    ├── __init__.py
    └── commands/
        ├── __init__.py
        ├── init.py
        └── verify.py
```

`main.py` becomes argparse + dispatch only. Each subcommand has its own module with a top-level `run(args)` entry function.

**Tach / importlinter** treat `mcp_tools_sql.cli` as part of the existing `entry_point` layer (same level as `main`). No new architectural layer; just two new module entries.

### 2. `verify` command pattern (mirrors `mcp-coder verify`)

Per-domain `verify_X()` functions return structured dicts; a central CLI formatter handles presentation.

**Function shape:**
```python
def verify_environment() -> dict[str, Any]: ...
def verify_config_files(config_path, db_config_path) -> dict[str, Any]: ...
def verify_dependencies(backend: str) -> dict[str, Any]: ...
def verify_builtin() -> dict[str, Any]: ...
def verify_connection(connection: ConnectionConfig) -> dict[str, Any]: ...
def verify_queries(queries, backend) -> dict[str, Any]:   # M2
def verify_updates(updates, backend) -> dict[str, Any]:   # M2
```

**Return shape** (plain dict, no Pydantic):
```python
{
    "<key>": {"ok": bool, "value": str, "error": str, "install_hint": str},
    ...
    "overall_ok": bool,
}
```

**Formatter** in `cli/commands/verify.py`:
- `STATUS_SYMBOLS = {"ok": "[OK]", "err": "[ERR]", "warn": "[WARN]"}`
- `_pad(text, width)` — left-pad/truncate
- `_format_row(status, label, value, error)` — one-line row formatter
- `_compute_exit_code(error_count)` — `0` or `1`
- Output via `print()` (deterministic terminal text). Internal diagnostics use `logger.debug()`.

### 3. Config-model cleanup

| Before | After |
|---|---|
| `ConnectionConfig.connection_string: str` | **removed** |
| (no `driver`) | `ConnectionConfig.driver: str = "ODBC Driver 18 for SQL Server"` (MSSQL only) |
| `UserConfig` | `DatabaseConfig` |
| `load_user_config()` | `load_database_config()` |
| `--user-config` CLI flag | `--database-config` |
| `_SENSITIVE_KEYS` includes `connection_string` | removed |
| `SQLiteBackend.connect()` reads `config.connection_string` | reads `config.path` |

No temporary compat shim — fixtures and code change atomically in the same step.

### 4. New mandatory runtime dep

`tomlkit` — required for `init --pyproject` to round-trip `pyproject.toml` with formatting/comments preserved. Stdlib `tomllib` is read-only.

### 5. `init` design

- Standalone TOML output uses **plain string templates** (multi-line f-strings). Simple, easy to read.
- `--pyproject` path uses **tomlkit** to insert `[tool.mcp-tools-sql]`. Refuses if section exists.
- Both project file (`mcp-tools-sql.toml`) and database config file (`~/.mcp-tools-sql/config.toml`) use `connection = "default"` / `[connections.default]` so the project resolves out-of-the-box.
- Database config file is written only if absent (skip-with-message if present).

### 6. `verify` M1 / M2 sections

| Section | Milestone | Content |
|---|---|---|
| `=== ENVIRONMENT ===` | M1 | Python version, virtualenv, package versions |
| `=== CONFIG ===` | M1 | Both config paths, parse status, sensitive-key warning |
| `=== DEPENDENCIES ===` | M1 | Backend extras only (sqlite: none; mssql: `pyodbc` + ODBC driver substring; postgresql: `psycopg`) |
| `=== BUILTIN ===` | M1 | `default_queries.toml` loaded, count of registered tools |
| `=== CONNECTION ===` | M1 | Backend, driver, host/path, database, credentials resolve, `SELECT 1` |
| `=== INSTALL INSTRUCTIONS ===` | M1 | Aggregated `install_hint` from failed entries |
| `=== QUERIES ===` | M2 | Per query: `EXPLAIN`, params well-formed, `max_rows` set |
| `=== UPDATES ===` | M2 | Per update: table/key/field columns exist (INFORMATION_SCHEMA / pragma_table_info) |

If `=== CONNECTION ===` fails, M2 sections are replaced with one summary line:
`connection failed; skipped N query checks, M update checks`.

Unimplemented backend → regular `[ERR]` (no `[SKIP]`), via existing `create_backend` `ValueError`.

---

## Files to Create

| Path | Purpose |
|---|---|
| `src/mcp_tools_sql/cli/__init__.py` | Package marker |
| `src/mcp_tools_sql/cli/commands/__init__.py` | Package marker |
| `src/mcp_tools_sql/cli/commands/init.py` | `init` subcommand |
| `src/mcp_tools_sql/cli/commands/verify.py` | `verify` subcommand + formatter |
| `tests/cli/__init__.py` | Package marker |
| `tests/cli/test_init.py` | Tests (i)–(vi) |
| `tests/cli/test_verify.py` | Tests (vii)–(xiv) |
| `pr_info/steps/step_1.md` … `step_9.md` | This implementation plan |

## Files to Modify

| Path | Reason |
|---|---|
| `src/mcp_tools_sql/main.py` | Argparse + dispatch only; rename `--user-config`; setup_logging once |
| `src/mcp_tools_sql/config/models.py` | Drop `connection_string`, add `driver`; rename `UserConfig` → `DatabaseConfig` |
| `src/mcp_tools_sql/config/loader.py` | Rename `load_user_config` → `load_database_config`; remove `connection_string` from `_SENSITIVE_KEYS` |
| `src/mcp_tools_sql/config/__init__.py` | Update exports for renames |
| `src/mcp_tools_sql/backends/sqlite.py` | Read `config.path` |
| `tests/backends/test_sqlite.py` | Migrate `connection_string=` → `path=` (~10 usages) |
| `tests/config/test_loader.py` | Update for renames + remove `connection_string` from sensitive-key tests |
| `tests/config/test_models.py` | Update for `UserConfig` → `DatabaseConfig` rename |
| `pyproject.toml` | Add `tomlkit` to runtime dependencies |
| `tach.toml` | Add `mcp_tools_sql.cli` and `mcp_tools_sql.cli.commands` modules under `entry_point` |
| `.importlinter` | Add `cli` to layered architecture contract (same level as `main`) |
| `mcp-tools-sql.md` | § 6 auth-methods table: remove "Connection string" row; § 6 config discovery: rename `--user-config` |

---

## Step Sequence

1. **Step 1** — Rename `UserConfig` → `DatabaseConfig`, `load_user_config` → `load_database_config`, `--user-config` → `--database-config`.
2. **Step 2** — Drop `connection_string`, add `driver`, fix `SQLiteBackend.connect()`, migrate test fixtures, planning doc § 6.
3. **Step 3** — Add `tomlkit` dep, create `cli/` package, refactor `main.py` to dispatch, update tach/importlinter.
4. **Step 4** — Implement `init` command (standalone TOML + `~/.mcp-tools-sql/config.toml` + `--pyproject`).
5. **Step 5** — `verify` skeleton: formatter helpers + `verify_environment` + `verify_config_files`.
6. **Step 6** — `verify`: `verify_dependencies` + `verify_builtin`.
7. **Step 7** — `verify`: `verify_connection` + `=== INSTALL INSTRUCTIONS ===` + skip-M2-on-failure summary.
8. **Step 8** — `verify` M2: `verify_queries`.
9. **Step 9** — `verify` M2: `verify_updates`.

Each step = one commit, all checks (pylint, pytest, mypy) passing.

---

## Quality Gates (after every step)

- `mcp__tools-py__run_pylint_check`
- `mcp__tools-py__run_pytest_check(extra_args=["-n", "auto", "-m", "not git_integration and not claude_cli_integration and not claude_api_integration and not formatter_integration and not github_integration and not langchain_integration"])`
- `mcp__tools-py__run_mypy_check`
- `mcp__tools-py__run_tach_check`
- `mcp__tools-py__run_lint_imports_check`

All must pass before moving to the next step.
