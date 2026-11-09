# Summary — Issue #94: verify JSON output, short summary, MCP tool and typed public API

## Goal

`mcp-tools-sql verify` (`cli/commands/verify.py` → `mcp_tools_sql.verification.verify_all`)
becomes usable by three new consumers:

- **Python callers**: a typed, documented `verify_all` result.
- **Scripts / CI**: `verify --output-format json`.
- **The LLM**: a `verify` MCP tool that returns a short summary.

Verify also stops letting one bad `[queries.*]` / `[updates.*]` entry hide every other check.

Default text output stays as it is today. `tests/cli/fixtures/verify_snapshot.txt`
and `tests/cli/test_verify.py` stay unchanged and must keep passing.

## Architectural / design changes

### 1. Typed result shape (replaces untyped dicts)

All types live in `verification/_helpers.py`, where `VerifierEntry` lives today.
`VerifierEntry` is removed.

```python
class CheckResult(TypedDict):          # one row; subset of mcp-workspace's CheckResult
    ok: bool
    value: str
    severity: Literal["error", "warning"]
    error: NotRequired[str]            # omitted when empty
    install_hint: NotRequired[str]     # omitted when empty

class VerifySection(TypedDict):
    title: str
    ok: bool
    checks: dict[str, CheckResult]     # ordered, keyed by row label

class VerifySummary(TypedDict):
    connections: dict[str, bool]       # connection -> all its database probes passed; {} if targets unresolved
    query_count: int                   # valid entries only
    update_count: int                  # valid entries only
    allow_updates: bool | None         # None = database config failed to parse

class VerifyResult(TypedDict):
    sections: list[VerifySection]
    skipped_queries: int | None        # None = QUERIES/UPDATES not skipped by a failed connection
    skipped_updates: int | None
    summary: VerifySummary
```

- WARN rows (`warn=True` today, with either `ok` value) become `ok=False, severity="warning"`.
  Passing rows and ERR rows have `severity="error"`.
- **One passing rule:** `is_passing(row) = row["ok"] or row["severity"] == "warning"`, and
  `checks_ok(checks) = all(is_passing(r) for r in checks.values())`. This rule decides:
  - every section's `ok`;
  - per-target reachability (`pair_ok`, `default_ok`, `reachable`);
  - CONNECTION's `ok`;
  - the pinned read-only check in `verify_one_query`.

  So a warning row never makes a target unreachable and never skips EXPLAIN.
- The per-section `verify_*` functions return `dict[str, CheckResult]`, with no
  `overall_ok` among the rows. The orchestrator wraps each one into a `VerifySection`.
  These functions stay importable but carry no stability promise.
- The skip summary becomes counts (`skipped_queries` / `skipped_updates`). The CLI renders
  the familiar sentence from them.

### 2. Config loaded once, entry by entry, under `project_dir`

- `verify_config_files(config_path, db_config_path, project_dir)` becomes the single place
  verify loads configs. It returns a NamedTuple
  `LoadedConfigs(checks, query_config, db_config, allow_updates)`:
  - Top-level query config is validated without `queries` / `updates`. Its result is the
    `query_config_parse` row.
  - Each `[queries.*]` / `[updates.*]` entry is validated on its own. An invalid entry gets
    the CONFIG row `queries.<name>.parse` / `updates.<name>.parse`.
  - A `queries` / `updates` value that is not a table gets the CONFIG row
    `queries.parse` / `updates.parse`, and that kind counts as zero entries.
  - `query_config` holds valid entries only. `db_config` is `None` when the file is absent
    or failed to parse, as today.
- `verify_all(config_path, db_config_path, project_dir=None)` calls it once and shares the
  result with every later section: target resolution, DEPENDENCIES, CONNECTION, QUERIES,
  UPDATES, skip counts and summary. The three `_load_query_config_*` /
  `_resolve_targets_for_verify` helpers in `orchestrator.py` are deleted. `Path.cwd()` is
  gone from `verification/`.
- Server startup is unchanged: `load_query_config` still validates the whole file and
  rejects it on any error.

### 3. Credentials hidden in validation errors

`model_config = ConfigDict(hide_input_in_errors=True)` on `DatabaseConfig` and on
`ConnectionConfig`. This keeps passwords out of CONFIG rows, the MCP tool output and the
server startup log. Query and update models are unchanged.

### 4. Rendering

- New `verification/render.py` holds:
  - `STATUS_SYMBOLS`, `LABEL_WIDTH`, `format_row` (moved from the CLI);
  - `row_status(row) -> "ok" | "warn" | "err"`;
  - `render_short(result) -> str`, the one short-summary renderer used by both
    `verify --short` and the MCP tool.
- The full text printer stays in `cli/commands/verify.py`. It imports `format_row` /
  `LABEL_WIDTH` under the old private names `_format_row` / `_LABEL_WIDTH`, so the
  unchanged CLI tests keep working.
- Short summary format (decided here):
  - First line: `"<config> Connections: <...>. <entries>."`
    - `<config>` is `Config loaded.` or `Config has errors.`, from CONFIG's `ok`.
    - Connections reads `A, B reachable; C unreachable`, or
      `not checked (targets unresolved)` when CONNECTION is absent.
    - Entries reads `12 queries, 3 updates OK`. When the two kinds differ:
      `12 queries OK, 3 updates with errors`. The possible states are `OK`,
      `with errors`, `not checked (connection failed)` and `not checked`.
    - When `allow_updates` is false, the updates part ends in
      `(not exposed: allow_updates=false)`.
  - Then, for each section that has ERR or WARN rows: a blank line, `=== TITLE ===`, and
    those rows formatted with `format_row`.
  - Built only from sections (by title / `ok`) and the summary block. Row labels are
    never parsed.
- `--short` prints only `render_short` output, without the trailing "N checks passed"
  line.

### 5. CLI flags on `verify`

- `--output-format text|json` (default `text`). `json` prints `json.dumps(result, indent=2)`
  of the exact `verify_all` result.
- `--short` changes text output only.
- Exit codes are unchanged in every mode: 0 = no ERR rows, 1 = any ERR row,
  2 = argparse error.
- `run()` reads the new flags with `getattr(args, ..., default)`, because the unchanged CLI
  tests build a `Namespace` without them.

### 6. MCP tool `verify` (server layer)

- `ToolServer.__init__` and `create_server` get keyword-only
  `query_config_path: Path | None = None` and `database_config_path: Path | None = None`.
  `build_tool_server` passes the resolved `qpath` and `args.database_config`.
- `_register_builtin_tools` adds a zero-argument async `verify` tool. It calls
  `verify_all(query_config_path, database_config_path)`, which re-reads the files from
  disk with its own `BackendRegistry`, and returns `render_short(result)` plus a fixed
  restart note. It is wrapped in `log_tool_call("verify")`, like the other tools.
  - It runs synchronously, like the other tools' backend calls.
  - It never touches the server's registry.
- `"verify"` is added to `PROGRAMMATIC_BUILTIN_TOOLS`.
- `tach.toml`: the server gets `mcp_tools_sql.verification` and
  `mcp_tools_sql.tool_logging` in `depends_on`. `.importlinter` already allows both.
- Configured tools are always registered as `query_<name>` / `update_<name>`. A test
  asserts that no built-in tool name starts with those prefixes.

### 7. Public API

`mcp_tools_sql.verification` exports `verify_all`, `CheckResult`, `VerifySection`,
`VerifySummary` and `VerifyResult` as the stable API. They are documented in the new
`docs/python-api.md`. `make_entry` and the other helpers stay private.

## Files created / modified

| Path | Change | Step |
|------|--------|------|
| `src/mcp_tools_sql/verification/_helpers.py` | types, `make_entry` severity, warn builders, `is_passing`, `checks_ok`, `VerifySummary` | 1, 3 |
| `src/mcp_tools_sql/verification/environment.py`, `dependencies.py`, `builtin.py`, `connection.py`, `queries.py`, `updates.py` | return checks only; passing rule | 1 |
| `src/mcp_tools_sql/verification/config_files.py` | checks only (1); `LoadedConfigs`, per-entry loading, `project_dir` (3) | 1, 3 |
| `src/mcp_tools_sql/verification/orchestrator.py` | `VerifyResult`, skip counts (1); load once, `project_dir`, summary (3) | 1, 3 |
| `src/mcp_tools_sql/verification/__init__.py` | public exports | 4 |
| `src/mcp_tools_sql/verification/render.py` | **new**: `format_row`, `row_status`, `render_short` | 5 |
| `src/mcp_tools_sql/cli/commands/verify.py` | new shape (1); `--output-format` (4); `--short` (5) | 1, 4, 5 |
| `src/mcp_tools_sql/config/models.py` | `hide_input_in_errors` | 2 |
| `src/mcp_tools_sql/server.py` | path kwargs, `verify` tool | 6 |
| `src/mcp_tools_sql/schema_tools.py` | `"verify"` in `PROGRAMMATIC_BUILTIN_TOOLS` | 6 |
| `tach.toml` | server `depends_on` | 6 |
| `tests/verification/test_*.py` | rewrite `overall_ok` / `warn` / tuple assertions; new tests | 1, 3 |
| `tests/verification/test_loading.py` | **new**: per-entry loading, summary, `project_dir` | 3 |
| `tests/verification/test_render.py` | **new**: `render_short` | 5 |
| `tests/config/test_models.py` | credentials hidden | 2 |
| `tests/cli/test_verify_output.py` | **new**: JSON + `--short` CLI tests | 4, 5 |
| `tests/test_server_verify_tool.py` | **new**: MCP tool, name-prefix guard | 6 |
| `docs/python-api.md` | **new** | 4 |
| `docs/cli.md` | `verify` flags, per-entry rows, MCP `verify` tool | 3, 4, 5, 6 |
| `docs/architecture/architecture.md` | result shape, server → verification edge | 1, 6 |

## Steps

1. Typed rows and sections; `verify_all` returns `VerifyResult` with skip counts.
2. Hide credentials in database-config validation errors.
3. Load configs once, entry by entry, under `project_dir`; summary block.
4. Public API exports, `--output-format json`, `docs/python-api.md`.
5. `render_short` and `verify --short`.
6. MCP tool `verify`.

## Checks after every step

Run `run_pylint_check`, `run_pytest_check` (`extra_args: ["-n", "auto"]`), `run_mypy_check`,
`run_ruff_check`, `run_lint_imports_check`, `run_tach_check` and `run_format_code`. All must
pass before the step's single commit.
