# Step 4 — Implement `init` command

**Reference**: [summary.md](./summary.md) — section "`init` design"
**Commit**: 4 of 10
**Goal**: `init` writes a starter `mcp-tools-sql.toml`, optionally appends to `pyproject.toml`, and writes a database config file at `~/.mcp-tools-sql/config.toml` if absent.

Covers tests (i)–(vi) from the issue.

> **Decision**: keep **two separate template builders** — `_build_project_template_standalone(backend)` and `_build_project_template_pyproject(backend)`. Do **not** factor into a shared `_build_project_template(comments=...)`. The two outputs have intentionally different content (full commented examples standalone vs. minimal active-keys-only inside pyproject) and a shared helper would obscure that.

---

## WHERE

Modify:
- `src/mcp_tools_sql/cli/commands/init.py` — replace `NotImplementedError` with full implementation
- `tests/cli/test_init.py` (new file)

---

## WHAT — Function signatures

```python
# cli/commands/init.py
from pathlib import Path
import argparse

BACKENDS = ("sqlite", "mssql", "postgresql")


def run(args: argparse.Namespace) -> int:
    """Dispatch to standalone or pyproject mode."""
    backend: str = args.backend
    if args.pyproject:
        return _run_pyproject(backend)
    return _run_standalone(backend, args.output)


def _run_standalone(backend: str, output: Path) -> int: ...
def _run_pyproject(backend: str) -> int: ...

def _build_project_template_standalone(backend: str) -> str: ...  # mcp-tools-sql.toml content (full, with commented examples)
def _build_project_template_pyproject(backend: str) -> str: ...    # minimal block content for [tool.mcp-tools-sql] (active keys + comment pointer to standalone template)
def _build_database_config_template(backend: str) -> str: ...      # ~/.mcp-tools-sql/config.toml content

def _write_database_config_if_absent() -> None:              # writes if missing, prints "left untouched" if present
    """Use Path.home() / ".mcp-tools-sql" / "config.toml"."""
```

---

## HOW — Templates (string literals)

### Project file (`mcp-tools-sql.toml`)

Common header for **all** backends:
```toml
connection = "default"

# Example SELECT query (uncomment to enable):
# [queries.get_user]
# description = "Look up a user by id"
# sql = "SELECT * FROM users WHERE id = :id"
# max_rows = 1
#
# [queries.get_user.params.id]
# name = "id"
# type = "int"
# description = "User id"
# required = true

# Example UPDATE definition (uncomment to enable):
# [updates.set_user_email]
# description = "Update a user's email"
# schema = "dbo"
# table = "users"
#
# [updates.set_user_email.key]
# field = "id"
# type = "int"
# description = "User id"
#
# [[updates.set_user_email.fields]]
# field = "email"
# type = "str"
# description = "New email"

# Default schema-introspection queries auto-load from the package.
# Uncomment any block below to override the default for a specific query.
# [queries.read_schemas]
# sql = "..."
#
# [queries.read_tables]
# sql = "..."
# (etc — see src/mcp_tools_sql/default_queries.toml for the full set)
```

### Database config file per backend

**sqlite**:
```toml
[connections.default]
backend = "sqlite"
path = "./mydb.db"
```

**mssql**:
```toml
[connections.default]
backend = "mssql"
host = ""
port = 1433
database = ""
username = ""
credential_env_var = "MSSQL_PASSWORD"
driver = "ODBC Driver 18 for SQL Server"
```

**postgresql**:
```toml
[connections.default]
backend = "postgresql"
host = ""
port = 5432
database = ""
username = ""
credential_env_var = "POSTGRES_PASSWORD"
```

The project file template is **identical for all backends** (no backend-specific section in `mcp-tools-sql.toml` — backend is in the database config).

---

## ALGORITHM — `_run_standalone`

```
if output already exists:
    print error, return 1
write _build_project_template(backend) to output
print f"Wrote {output}"
_write_database_config_if_absent(backend)
return 0
```

## ALGORITHM — `_run_pyproject`

> When `--pyproject` is set, `--output` is ignored — the project block is written into `pyproject.toml`'s `[tool.mcp-tools-sql]` table, not to a separate file. If `--output` was supplied with a non-default value, log a `logger.debug(...)` line acknowledging it was ignored. No error, no warning to stdout.

```
pyproject = Path("pyproject.toml")
if not pyproject.exists():
    print error, return 1
doc = tomlkit.parse(pyproject.read_text())
if "tool" in doc and "mcp-tools-sql" in doc["tool"]:
    print "[tool.mcp-tools-sql] already exists in pyproject.toml — refusing to overwrite", return 1
ensure doc["tool"] table exists
build a tomlkit table for "mcp-tools-sql" with the same content as project template (TOML keys / commented examples preserved via tomlkit comments)
doc["tool"]["mcp-tools-sql"] = table
pyproject.write_text(tomlkit.dumps(doc))
print "Appended [tool.mcp-tools-sql] to pyproject.toml"
_write_database_config_if_absent(backend)   # also writes the db config when --pyproject is used
return 0
```

The `--pyproject` inserted block contains the **active** keys only (`connection = "default"`) plus a single comment line pointing the user at the standalone template, e.g.:

```
# For commented examples of [queries.*] / [updates.*] blocks,
# see the standalone mcp-tools-sql.toml template (run `mcp-tools-sql init` without --pyproject).
```

This is produced by `_build_project_template_pyproject(backend)`.

## ALGORITHM — `_write_database_config_if_absent`

```
path = Path.home() / ".mcp-tools-sql" / "config.toml"
if path.exists():
    print "Existing ~/.mcp-tools-sql/config.toml left untouched."
    return
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(_build_database_config_template(backend))
print f"Wrote {path}"
```

---

## DATA — Exit codes

- `0` — success (file written, or skipped because already existed in the case of db config)
- `1` — refused (output file already exists; pyproject section already exists; pyproject.toml not found)

---

## Tests — `tests/cli/test_init.py`

Use `tmp_path` and `monkeypatch.setenv("HOME", str(tmp_path))` (or monkeypatch `Path.home`) to redirect the database config write target.

| # | Test | Asserts |
|---|---|---|
| (i) | `test_init_generates_valid_toml` | Output parses with `tomllib` and has `connection = "default"` |
| (ii) | `test_init_sqlite_uses_path` (parametrize: sqlite, mssql, postgresql) | Database config file uses `path` for sqlite, `host`/`port` for mssql/postgresql |
| (iii) | `test_init_pyproject_happy_path` | Existing `pyproject.toml` gains `[tool.mcp-tools-sql]` |
| (iii.b) | `test_init_pyproject_block_contains_pointer_comment` | The inserted `[tool.mcp-tools-sql]` block contains the comment-pointer text referencing the standalone `mcp-tools-sql.toml` template (assert on substring like `"standalone mcp-tools-sql.toml template"`) |
| (iv) | `test_init_pyproject_refuses_when_section_exists` | Returns 1, pyproject content unchanged |
| (v) | `test_init_does_not_overwrite_existing_database_config` | When file exists, prints "left untouched", file unchanged |
| (vi) | `test_init_writes_default_in_both_files` | `mcp-tools-sql.toml` has `connection = "default"` AND `~/.mcp-tools-sql/config.toml` has `[connections.default]` |

Plus:
- `test_init_refuses_when_output_exists`
- `test_init_pyproject_when_no_pyproject` (returns 1 with clear message)

---

## Quality gates

All five checks green.

---

## LLM Prompt for this step

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_4.md`. Implement the `init` subcommand in `src/mcp_tools_sql/cli/commands/init.py` per the spec: standalone TOML output via plain string templates, `--pyproject` path via `tomlkit` (refuse if `[tool.mcp-tools-sql]` already exists), and writing of `~/.mcp-tools-sql/config.toml` (skip-with-message if already present). Use `connection = "default"` and `[connections.default]` consistently in both files. Per-backend database config templates: SQLite uses `path = "./mydb.db"`; MSSQL adds `port = 1433`, `credential_env_var = "MSSQL_PASSWORD"`, `driver = "ODBC Driver 18 for SQL Server"`; PostgreSQL adds `port = 5432`, `credential_env_var = "POSTGRES_PASSWORD"`. Return exit code 0 on success, 1 on refusal. Add `tests/cli/test_init.py` covering issue tests (i)–(vi) plus refuse-on-existing-output and refuse-on-missing-pyproject. Run all quality checks and ensure they pass.
