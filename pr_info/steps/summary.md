# Summary — #104 Library verify via the shared contract; build_toolset fails early

Part of agent-workbench#13; implements mcp-coder-utils#61 (verification contract).

## Goal

- A library consumer (agent-workbench) calls
  `mcp_tools_sql.toolset.verify(query_config, database_config=None, *, connect=False) -> list[VerifyItem]`
  and gets mcp-tools-sql's own checks as shared `VerifyItem` rows, with or
  without database access. It never raises for problems it detects.
- `build_toolset` raises `ValueError` for a broken setup (missing explicit
  database config, unsupported backend, missing `pyodbc`, configured ODBC
  driver not installed) before any tool is built – not at the model's first
  tool call.
- Invariant: if `verify(connect=False)` passes, `build_toolset` on the same
  paths succeeds (guaranteed by the `toolset.build` row, which runs the real
  build).

## Architectural / design changes

| Area | Before | After |
|---|---|---|
| Backend names | `_DIALECTS` in `backends/base.py`; `create_backend` dispatch kept "in sync" by comment; `pyodbc` alias only honoured by `create_backend` / `to_dialect` | `SUPPORTED_BACKENDS = frozenset(_DIALECTS)` and `normalize_backend()` (`pyodbc` → `mssql`) in `backends/base.py`; `create_backend` validates against the set, then dispatches on the normalised name. CONNECTION and UPDATES use `normalize_backend()` |
| Dependency check | `verification/dependencies.py` checks only the **default** target's backend; `psycopg` probe for postgresql | New `backends/connection_check.py`: `check_connections(connections) -> list[DependencyRow]` for **every** connection (neutral rows; `backends` cannot import `verification`). Used by the DEPENDENCIES section (rows keyed `<connection>.<key>`) and by `build_toolset`. `psycopg` probe and `backends/postgresql.py` removed (#29 re-adds them) |
| Database config loading | `load_database_config(path)` silently returns defaults for any missing path | An **explicit** missing path raises `ValueError` naming the path; `None` keeps the zero-config default |
| `build_toolset` | Loads, resolves, builds; problems surface at first tool call | After loading and before `BackendRegistry()`: raises `ValueError` on the first failing dependency row (names the connection, carries the hint). No connection is opened |
| Verification sections | CONNECTION always probes (DNS, `klist`, `select_1`); QUERIES always emits `<name>.sql` | `verify_connection(..., connect=False)` emits only config rows; `_verify_connections(targets, None)` creates no backends; `verify_queries(..., registry=None)` emits no `<name>.sql` rows (config-only mode) |
| Orchestrator | `verify_all` only | Shared `_head_sections()` (ENVIRONMENT, CONFIG, DEPENDENCIES, BUILTIN + loaded configs/targets). `verify_all` unchanged in signature, result, order and gating. New `collect_sections(config_path, db_config_path, *, connect, build_probe)` adds a TOOLSET section (`build` row) after BUILTIN, then CONNECTION, QUERIES, and UPDATES (only `connect=True`), with per-target gating instead of default-down gating |
| `toolset.build` row | – | `build_probe` callback injected by `toolset` (verification sits below toolset in the layers). Exception → `error` row; any earlier ERR row in the head sections → `warning` "skipped (earlier errors)" |
| Public library API | `verify_all` / `CheckResult` | `toolset.verify` maps sections to `VerifyItem`: `name = <section lowercased>.<key unchanged>`, status `ok`/`warning`/`error`, `message = "value - error"`, `hint = install_hint or None`. INSTALL INSTRUCTIONS is never produced by `collect_sections` |
| Shared type | – | `VerifyItem` from `mcp_coder_utils.toolkit` via new shim `utils/toolkit.py` (named after #61's current home; rename the shim if #61 moves the type). Imported **lazily** inside `verify` (toolkit imports `jsonschema`, ~125 ms, #39) |

Layering is unchanged: `toolset` → `verification` → `backends` → `config` →
`utils`. No `.importlinter` / `tach.toml` change beyond the `psycopg_isolation`
ignore removal; `utils.** -> mcp_coder_utils` is already allowed. `toolset`
still imports no `mcp`.

## Files

### Created
- `src/mcp_tools_sql/backends/connection_check.py` — per-connection dependency check
- `src/mcp_tools_sql/utils/toolkit.py` — shim re-exporting `VerifyItem`, `VerifyStatus`
- `tests/backends/test_connection_check.py`
- `tests/backends/test_backend_names.py`
- `tests/test_toolset_build_errors.py`
- `tests/test_toolset_verify.py`
- `tests/verification/test_collect_sections.py`

### Modified
- `src/mcp_tools_sql/backends/base.py` — `SUPPORTED_BACKENDS`, `normalize_backend`
- `src/mcp_tools_sql/backends/registry.py` — `create_backend` validation
- `src/mcp_tools_sql/verification/connection.py` — alias, `connect` flag
- `src/mcp_tools_sql/verification/updates.py` — alias in `_list_table_columns`
- `src/mcp_tools_sql/verification/dependencies.py` — per-connection rows
- `src/mcp_tools_sql/verification/queries.py` — `registry: BackendRegistry | None`
- `src/mcp_tools_sql/verification/orchestrator.py` — `_head_sections`, `collect_sections`
- `src/mcp_tools_sql/config/loader.py` — explicit missing path raises
- `src/mcp_tools_sql/toolset.py` — early dependency check, `verify`
- `.importlinter` — `psycopg_isolation`: drop `ignore_imports`, update comment
- `pyproject.toml` — `[tool.deptry] per_rule_ignores = { DEP002 = ["psycopg"] }`
- Tests: `tests/backends/test_registry.py`, `tests/backends/test_dependency_probes.py`,
  `tests/verification/test_dependencies.py`, `tests/verification/test_connection.py`,
  `tests/verification/test_queries.py`, `tests/verification/test_updates.py`,
  `tests/cli/test_verify.py`, `tests/config/test_loader.py`, `tests/test_module_imports.py`
- Docs: `docs/python-api.md`, `docs/architecture/architecture.md`,
  `docs/quality-and-security-checks.md`, `docs/cli.md`, `docs/configuration.md`,
  `.claude/CLAUDE.md` (Shared Libraries list)

### Deleted
- `src/mcp_tools_sql/backends/postgresql.py`

## Steps

1. Backend names: supported set + `pyodbc` alias (base, registry, CONNECTION, UPDATES)
2. Per-connection dependency check; DEPENDENCIES per connection; remove psycopg probe
3. `load_database_config`: explicit missing path raises
4. `build_toolset` fails early on dependency errors
5. Config-only section parameters (CONNECTION `connect`, QUERIES `registry=None`)
6. Orchestrator: shared head + `collect_sections` with `toolset.build` row
7. Public `toolset.verify` + `utils/toolkit.py` shim
8. Docs

Every step: tests first, then implementation; run `run_format_code`, pylint,
pytest (`extra_args: ["-n", "auto"]`), mypy, ruff, and the architecture
checks named in the step; one commit per step.
