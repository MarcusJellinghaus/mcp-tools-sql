# Step 3 — Load configs once, entry by entry, under `project_dir`; summary block

## LLM prompt

> Read `pr_info/steps/summary.md` (sections 1–2), then implement **this step only**
> (`pr_info/steps/step_3.md`). Do TDD: write the new tests in
> `tests/verification/test_config_files.py` and `tests/verification/test_orchestrator.py`
> first, then implement. Default text output for valid configs must
> stay unchanged; `tests/cli/test_verify.py` must not be edited and must pass. Run pylint,
> pytest (`-n auto`), mypy, ruff, lint-imports, tach and format_code, then make one commit.

## WHERE

- `src/mcp_tools_sql/verification/_helpers.py` (add `VerifySummary`; add `summary` to `VerifyResult`)
- `src/mcp_tools_sql/verification/config_files.py`
- `src/mcp_tools_sql/verification/orchestrator.py`
- `tests/verification/test_config_files.py`, `tests/verification/test_orchestrator.py`
- `docs/cli.md` (`CONFIG` row of the verify sections table)
- `docs/architecture/architecture.md` (`VerifyResult` description from step 1)

## WHAT

```python
# _helpers.py
class VerifySummary(TypedDict):
    connections: dict[str, bool]
    query_count: int
    update_count: int
    allow_updates: bool | None

class VerifyResult(TypedDict):
    sections: list[VerifySection]
    skipped_queries: int | None
    skipped_updates: int | None
    summary: VerifySummary

# config_files.py
class LoadedConfigs(NamedTuple):
    checks: dict[str, CheckResult]
    query_config: QueryFileConfig | None   # top level valid; only valid entries
    db_config: DatabaseConfig | None       # None when file absent or parse failed
    allow_updates: bool | None             # None when parse failed; default when absent

def verify_config_files(config_path: Path | None, db_config_path: Path | None,
                        project_dir: Path) -> LoadedConfigs
def _load_entries(data: dict[str, object], kind: str, model: type[BaseModel],
                  checks: dict[str, CheckResult]) -> dict[str, Any]

# orchestrator.py
def verify_all(config_path: Path | None, db_config_path: Path | None,
               project_dir: Path | None = None) -> VerifyResult
```

Delete `_resolve_targets_for_verify`, `_load_query_config_for_counts` and
`_load_query_config_for_m2`.

## HOW

- `verify_config_files`:
  - discover with `discover_query_config(config_path, project_dir=project_dir)`;
  - read the raw mapping once with `read_query_config_data`, and reuse it for the
    sensitive-key scan;
  - validate with `QueryFileConfig.model_validate` / `QueryConfig.model_validate` /
    `UpdateConfig.model_validate`, without calling `load_query_config`, so no warning is
    logged;
  - load the DB config with `load_database_config(db_path)` only when the file exists.
- Cross-file checks run when `query_config` and `db_config` are both not `None`. They walk
  valid entries only.
- `verify_all`:
  - `project_dir = project_dir or Path.cwd()`;
  - `targets = resolve_targets(loaded.query_config, loaded.db_config)` when both are set,
    with `ValueError` caught and logged at debug level as today;
  - the backend for DEPENDENCIES comes from those targets as today.

## ALGORITHM

`verify_config_files`, query half:

```
path = discover(...)  -> query_config_path row (on error: path row + "skipped" parse row, as today)
data = read_query_config_data(path)            # ValueError -> query_config_parse ERR
top = QueryFileConfig.model_validate({k: v for k, v in data.items() if k not in ("queries", "updates")})
checks["query_config_parse"] = ok row "loaded"  # ValidationError -> ERR row, query_config = None
if top validated:
    queries = _load_entries(data, "queries", QueryConfig, checks); updates = _load_entries(data, "updates", UpdateConfig, checks)
    query_config = top.model_copy(update={"queries": queries, "updates": updates})
sensitive-keys row from data (whenever data was read)
```

When top-level validation fails, entries are not validated: no `queries.parse`,
`updates.parse`, `queries.<name>.parse` or `updates.<name>.parse` rows are emitted,
`query_config` is `None`, and the summary's `query_count` / `update_count` are `0`.

`_load_entries`:

```
raw = data.get(kind, {})
if not isinstance(raw, dict): checks[f"{kind}.parse"] = make_entry(ok=False, error=f"`{kind}` must be a table"); return {}
valid = {}
for name, entry in raw.items():
    try: valid[name] = model.model_validate(entry)
    except ValidationError as exc: checks[f"{kind}.{name}.parse"] = make_entry(ok=False, error=str(exc))
return valid
```

Summary block in `verify_all`:

```
connections = {}
for (conn, _db), ok in reachable.items(): connections[conn] = connections.get(conn, True) and ok
qc = loaded.query_config
summary = {"connections": connections, "query_count": len(qc.queries) if qc else 0,
           "update_count": len(qc.updates) if qc else 0, "allow_updates": loaded.allow_updates}
skip counts (connection failed) = len(qc.queries), len(qc.updates)
```

## DATA

- Row order in CONFIG:
  1. `query_config_path`
  2. `query_config_parse`
  3. `queries.parse` / `queries.<name>.parse` rows
  4. `updates.parse` / `updates.<name>.parse` rows
  5. `query_config_sensitive_keys`
  6. `database_config_path`
  7. `database_config_parse`
  8. cross-file rows

  Valid configs produce exactly today's rows.
- `allow_updates`:
  - file absent: `DatabaseConfig().security.allow_updates`, i.e. `True`;
  - parsed: `db_config.security.allow_updates`;
  - parse error: `None`.

## Tests (write first)

`tests/verification/test_config_files.py` (`verify_config_files`, tmp configs):

- Existing calls become `verify_config_files(q, db, project_dir=tmp_path)`, and
  assertions read `result.checks[...]`.
- One valid and one invalid `[queries.*]` entry (`[queries.bad]` with no `sql`): an ERR
  row `queries.bad.parse`, `query_config_parse` OK, and `result.query_config.queries`
  holds the valid entry only.
- Invalid `[updates.bad]` entry (`fields = "x"`): an `updates.bad.parse` row; valid
  queries stay in `result.query_config`.
- `queries = 5`: a `queries.parse` row, `query_config_parse` OK, and
  `result.query_config.queries == {}`.
- Top-level validation fails (e.g. `connection = 5`) alongside an invalid `[queries.bad]`
  entry: `query_config_parse` is ERR, no `queries.parse` / `queries.<name>.parse` /
  `updates.parse` / `updates.<name>.parse` rows, and `result.query_config is None`.
- `allow_updates`: `[security]\nallow_updates = false` gives `False`; an invalid
  database config gives `None`; an absent database config file gives `True`.
- `project_dir`: put `mcp-tools-sql.toml` in `tmp_path / "proj"`, call with
  `config_path=None, project_dir=tmp_path / "proj"`, and `query_config_path` is that file.

`tests/verification/test_orchestrator.py` (`verify_all` with tmp sqlite configs and the
`sqlite_db` fixture):

- The result has a `summary` key with the four fields.
- One valid and one invalid `[queries.*]` entry: DEPENDENCIES has no failing rows,
  CONNECTION is present, and QUERIES has rows for the valid query only.
- `queries = 5`: CONNECTION present, UPDATES still runs, and
  `summary["query_count"] == 0`.
- Top-level validation fails: `summary["query_count"] == 0` and
  `summary["update_count"] == 0`.
- Failed connection (sqlite `path = ""`) with one valid and one invalid query:
  `skipped_queries == 1`.
- Summary block: a happy path gives `connections == {"default": True}` and the counts;
  `allow_updates = false` reaches `summary["allow_updates"]`; an invalid database config
  gives `allow_updates is None` and `connections == {}`.
- `project_dir`: `verify_all(None, db_cfg, project_dir=tmp_path / "proj")` with cwd
  elsewhere reports that directory's `mcp-tools-sql.toml` as `query_config_path`.

## Docs

`docs/cli.md`, `CONFIG` row of the verify sections table: mention the per-entry
`queries.<name>.parse` / `updates.<name>.parse` rows, and that a bad entry no longer
blocks the other checks.

`docs/architecture/architecture.md`, Verification Layer: extend the `VerifyResult`
sentence written in step 1 to include the `summary` block (connections, entry counts,
`allow_updates`).
