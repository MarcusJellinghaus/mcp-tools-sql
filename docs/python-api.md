# Python API

`mcp_tools_sql.verification` exposes the checks behind `mcp-tools-sql verify`
as a typed Python API. The stable surface is `verify_all` and four result
types: `CheckResult`, `VerifySection`, `VerifySummary` and `VerifyResult`.

The per-section functions (`verify_environment`, `verify_config_files`,
`verify_connection`, `verify_queries`, …) are importable but are **not** part
of the stable API: their signatures and return shapes may change in any
release.

## `verify_all`

```python
def verify_all(
    config_path: Path | None,
    db_config_path: Path | None,
    project_dir: Path | None = None,
) -> VerifyResult
```

- `config_path` — project query config. `None` discovers
  `mcp-tools-sql.toml`, else `[tool.mcp-tools-sql]` in `pyproject.toml`,
  under `project_dir`.
- `db_config_path` — database config. `None` uses
  `~/.mcp-tools-sql/config.toml`.
- `project_dir` — directory for query-config discovery. Defaults to the
  current directory.

The call is synchronous and typically takes seconds: it probes every
configured `(connection, database)` pair and `EXPLAIN`s every configured
query. It opens its own database connections and closes them before
returning; it never reuses a running server's connections. Every problem is
reported as a row in the result, not raised.

## Result types

All four are `TypedDict`s, so the result is plain dicts and lists and
serializes directly with `json.dumps` — this is what
`verify --output-format json` prints.

### `VerifyResult`

| Field | Type | Meaning |
|-------|------|---------|
| `sections` | `list[VerifySection]` | Sections in the order `verify` prints them (ENVIRONMENT, CONFIG, DEPENDENCIES, BUILTIN, CONNECTION, QUERIES, UPDATES, INSTALL INSTRUCTIONS). Sections that did not run are absent. |
| `skipped_queries` | `int \| None` | `None` unless QUERIES/UPDATES were skipped because the default connection failed; then the number of query entries left unchecked. |
| `skipped_updates` | `int \| None` | As `skipped_queries`, for update entries. |
| `summary` | `VerifySummary` | Condensed facts about the run. |

### `VerifySection`

| Field | Type | Meaning |
|-------|------|---------|
| `title` | `str` | Section title, e.g. `"CONNECTION"`. |
| `ok` | `bool` | `True` when every row in `checks` is passing (see below). |
| `checks` | `dict[str, CheckResult]` | Rows keyed by label, in print order. |

### `CheckResult`

| Field | Type | Meaning |
|-------|------|---------|
| `ok` | `bool` | The check passed. |
| `value` | `str` | What was found (a version, a path, `"EXPLAIN ok"`, …). |
| `severity` | `"error" \| "warning"` | `"warning"` marks a WARN row (always `ok=False`); passing rows and ERR rows have `"error"`. |
| `error` | `str`, optional | Why the check failed. Present only when non-empty. |
| `install_hint` | `str`, optional | How to fix a missing dependency. Present only when non-empty. |

A row is **passing** when `ok` is true or `severity == "warning"`. Warnings
never fail a section and never affect the exit code; any non-passing row is
an ERR.

### `VerifySummary`

| Field | Type | Meaning |
|-------|------|---------|
| `connections` | `dict[str, bool]` | Each connection name → `True` when all of its database probes passed. `{}` when the targets could not be resolved (a config failed to load, or the default connection is unknown). |
| `query_count` | `int` | Number of valid `[queries.*]` entries. Invalid entries appear as CONFIG rows instead. |
| `update_count` | `int` | Number of valid `[updates.*]` entries. |
| `allow_updates` | `bool \| None` | The database config's `allow_updates`; when `False` the server does not expose update tools. `None` when the database config failed to parse. |

## Example

```python
from pathlib import Path

from mcp_tools_sql.verification import verify_all

result = verify_all(Path("mcp-tools-sql.toml"), None)
for section in result["sections"]:
    for label, row in section["checks"].items():
        if not row["ok"] and row["severity"] == "error":
            print(f"{section['title']}: {label} - {row.get('error', '')}")

down = [name for name, ok in result["summary"]["connections"].items() if not ok]
```

## Exit codes

`verify` maps the result to exit codes the same way in every output format;
see [Exit codes](cli.md#exit-codes-1).
