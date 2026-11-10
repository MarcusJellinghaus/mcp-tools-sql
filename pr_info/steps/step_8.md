# Step 8 — Docs

## LLM prompt
Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_8.md`.
Docs only — no code changes. Read each file before editing and keep its style.
Run pytest (`extra_args: ["-n", "auto"]`) once to confirm nothing depends on doc
text. One commit: `docs: library verify, early build failures, per-connection dependencies`.

## WHERE / WHAT
- `docs/python-api.md`
  - Intro: the stable surface now also includes `mcp_tools_sql.toolset.verify`.
  - New `## verify` section: signature
    `verify(query_config: Path, database_config: Path | None = None, *, connect: bool = False) -> list[VerifyItem]`;
    `VerifyItem` from mcp-coder-utils (`name`, `status` ok/warning/error, `message`, `hint`);
    never raises for problems it detects.
  - `connect=False`: ENVIRONMENT, CONFIG, DEPENDENCIES (every connection),
    BUILTIN, `toolset.build`, config-only CONNECTION rows, config-only QUERIES
    rows; no connection, DNS lookup or subprocess; no placeholder rows.
  - `connect=True`: all of the above plus `dns_lookup`, `kerberos_ticket`,
    `select_1`, `<query>.sql`, UPDATES; unreachable targets get "skipped" rows.
  - Row names are opaque identifiers: `<section lowercased>.<key>` (examples
    from the summary); `message = "value - error"`; no INSTALL INSTRUCTIONS rows.
  - `toolset.build`: real build, closed again; "skipped (earlier errors)" warning.
- `docs/architecture/architecture.md`
  - Toolset section: `verify`; `build_toolset` raises `ValueError` early
    (missing explicit db config, unsupported backend, missing `pyodbc`, ODBC
    driver not installed), no connection opened.
  - Key Modules: drop the `backends/postgresql.py` row; add
    `backends/connection_check.py` (per-connection dependency check used by
    DEPENDENCIES and `build_toolset`); mention `SUPPORTED_BACKENDS` /
    `normalize_backend` in the `backends/base.py` row; `toolset.py` row gets `verify`;
    `query_tools.py` row: `verify` reports a non-read-only query as an error.
  - Architecture Enforcement: `psycopg` has no allowed importer until #29.
- `docs/quality-and-security-checks.md`: `psycopg_isolation` — no ignore; nothing
  may import psycopg until the PostgreSQL backend (#29); deptry DEP002 ignore for `psycopg`.
- `docs/cli.md`: DEPENDENCIES table cell — checks every connection, rows keyed
  `<connection>.<key>` (example `default.info`, `prod.pyodbc`, `prod.odbc_driver`),
  single `backend` row without a valid database config, unsupported backend
  (e.g. `postgresql`) is an ERR; drop "`psycopg` for `postgresql`"; update the
  example `info` row and any JSON-output example keys.
- `docs/configuration.md`: database-config resolution — an explicit
  `--database-config` path that does not exist is an error; `None` → default
  location, defaults when absent. `backend` table cell: any `postgresql`
  connection now fails startup (unsupported until #29), not only when a query targets it.
- `.claude/CLAUDE.md` "Shared Libraries": add `toolkit` to the shim list
  (`log_utils`, `user_app_data`, `subprocess_runner`, `tool_spec`, `toolkit`).
