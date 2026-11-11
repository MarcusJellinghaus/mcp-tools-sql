# Python API

`mcp_tools_sql.verification` exposes the checks behind `mcp-tools-sql verify`
as a typed Python API. The stable surface is `verify_all` and four result
types: `CheckResult`, `VerifySection`, `VerifySummary` and `VerifyResult`,
plus `mcp_tools_sql.toolset.verify`, which returns the checks as shared
`VerifyItem` rows for library consumers such as agent-workbench.

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

## `verify`

```python
from mcp_tools_sql.toolset import verify

def verify(
    query_config: Path,
    database_config: Path | None = None,
    *,
    connect: bool = False,
) -> list[VerifyItem]
```

Checks the setup `build_toolset` would use on the same paths.
`database_config=None` uses `~/.mcp-tools-sql/config.toml`. `verify` never
raises for problems it detects: each one becomes an `error` or `warning`
item.

`VerifyItem` is the verification contract shared across tool packages,
defined in `mcp_coder_utils.toolkit`:

| Field | Type | Meaning |
|-------|------|---------|
| `name` | `str` | Row identifier, see [Row names](#row-names). |
| `status` | `"ok" \| "warning" \| "error"` | As `verify`'s `[OK]` / `[WARN]` / `[ERR]`. |
| `message` | `str` | `"value - error"`, or whichever of the two is non-empty. |
| `hint` | `str \| None` | How to fix a missing dependency; `None` when there is none. |

### What runs

| `connect` | Checks |
|-----------|--------|
| `False` (default) | ENVIRONMENT, CONFIG, DEPENDENCIES (every connection), BUILTIN, `toolset.build`, the config rows of CONNECTION (backend, driver, host/port, database or path, credentials, connection string) and of QUERIES (read-only proof, params, `max_rows_*`). No connection is opened, no DNS lookup and no subprocess runs. The checks left out produce no rows, not placeholder rows. |
| `True` | All of the above, plus `dns_lookup`, `kerberos_ticket` and `select_1` per target, `<query>.sql` (`EXPLAIN`) per query, and UPDATES. A check against an unreachable target is a `warning` `skipped (connection <name> unreachable)`; the target's own probe carries the error. |

Items follow section order. There are no INSTALL INSTRUCTIONS items: the
hints are on the failing items themselves.

### `toolset.build`

Runs the real `build_toolset` on the same paths and closes the result again,
so when `verify(connect=False)` passes, `build_toolset` succeeds. A build
exception is an `error` item carrying its message. When an earlier item is
an `error`, the build is not attempted and the item is a `warning`
`skipped (earlier errors)`.

### Row names

Names are opaque identifiers: match them exactly, don't parse them. Each is
`<section lowercased>.<key>`, with the key as `verify` prints it, e.g.
`dependencies.prod.pyodbc`, `toolset.build`, `connection.prod/sales.select_1`,
`queries.orders_by_customer.read_only[mssql]`. Connection and query names
keep their case.

```python
from pathlib import Path

from mcp_tools_sql.toolset import verify

for item in verify(Path("mcp-tools-sql.toml")):
    if item.status == "error":
        print(item.name, item.message, item.hint or "")
```

## Exit codes

`verify` maps the result to exit codes the same way in every output format;
see [Exit codes](cli.md#exit-codes-1).
