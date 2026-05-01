# Step 1 — Rename `UserConfig` / `--user-config` → `DatabaseConfig` / `--database-config`

**Reference**: [summary.md](./summary.md) — section "Config-model cleanup"
**Commit**: 1 of 10
**Goal**: Pure rename. No behavior change.

---

## WHERE

Modify only:
- `src/mcp_tools_sql/config/models.py`
- `src/mcp_tools_sql/config/loader.py`
- `src/mcp_tools_sql/config/__init__.py`
- `src/mcp_tools_sql/main.py`
- `tests/config/test_models.py`
- `tests/config/test_loader.py`

---

## WHAT — Renames

| Old | New |
|---|---|
| `class UserConfig` (models.py) | `class DatabaseConfig` |
| `def load_user_config(path)` (loader.py) | `def load_database_config(path)` |
| `--user-config` (main.py argparse) | `--database-config` |
| `args.user_config` | `args.database_config` |
| `loader.py::resolve_connection(query_config, user_config: UserConfig)` | `resolve_connection(query_config, db_config: DatabaseConfig)` — **rename the parameter** from `user_config` to `db_config` and retype it. Update the docstring opening line *"Look up the named connection from user config."* → *"Look up the named connection from database config."* |

Default file path `~/.mcp-tools-sql/config.toml` is **unchanged**.

The docstring/`help=` text for the flag should change to: *"Path to database configuration file (connections, credentials)."*

---

## HOW — Integration points

- `loader.py`: function rename + update its return-type hint to `DatabaseConfig`. Update its imports.
- `loader.py::resolve_connection`: rename parameter `user_config: UserConfig` → `db_config: DatabaseConfig` (renamed per WHAT-table; update docstring accordingly).
- `config/__init__.py`: re-export `DatabaseConfig` (not `UserConfig`). Verify nothing else imports `UserConfig`.
- `main.py`: update `add_argument("--database-config", ...)`. The attribute name auto-becomes `args.database_config`.

---

## ALGORITHM

```
search project for "UserConfig" / "user_config" / "--user-config"
for each occurrence:
    if symbol → rename (use mcp__tools-py__rename_symbol where applicable)
    if string literal → replace
update CLI flag name + its help text
run all quality checks → must be green
```

---

## DATA — No data-shape changes

`DatabaseConfig` keeps the exact same fields as the old `UserConfig`:
```python
class DatabaseConfig(BaseModel):
    connections: dict[str, ConnectionConfig] = {}
    security: SecurityConfig = SecurityConfig()
```

---

## Tests — Update existing only

- `tests/config/test_models.py::TestModelValidation::test_user_config_defaults` → rename to `test_database_config_defaults`, use `DatabaseConfig`.
- `tests/config/test_loader.py::TestLoadUserConfig` → rename class to `TestLoadDatabaseConfig`; rename test methods; switch import to `load_database_config`.
- `tests/config/test_loader.py::TestResolveConnection` → update local fixtures to use `DatabaseConfig`.

No new tests in this step. The rename is verified by all existing tests still passing.

---

## Quality gates

After the rename, run **all** of:
- `mcp__tools-py__run_pylint_check`
- `mcp__tools-py__run_pytest_check` (with the standard exclusion markers — see CLAUDE.md)
- `mcp__tools-py__run_mypy_check`
- `mcp__tools-py__run_tach_check`
- `mcp__tools-py__run_lint_imports_check`

---

## LLM Prompt for this step

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_1.md`. Implement step 1: rename `UserConfig` → `DatabaseConfig`, `load_user_config` → `load_database_config`, and the CLI flag `--user-config` → `--database-config` (also `args.user_config` → `args.database_config`). The default file path `~/.mcp-tools-sql/config.toml` is unchanged. This is a pure rename — no behavior changes. Update existing tests accordingly. Run all quality checks (pylint, pytest with the standard exclusion markers, mypy, tach, lint-imports) and ensure they all pass before committing.
