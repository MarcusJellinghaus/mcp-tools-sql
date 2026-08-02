# Step 4 — Config resolution: `resolve_targets`

See `pr_info/steps/summary.md` → "Data structures" and "Two new collaborators".

## WHERE
- `src/mcp_tools_sql/config/models.py` (add `ResolvedTarget`, `ResolvedTargets`)
- `src/mcp_tools_sql/config/loader.py` (add `resolve_targets`)
- Tests: `tests/config/test_loader.py`, `tests/config/test_models.py`

## WHAT
```python
class ResolvedTarget(BaseModel):        # frozen
    connection: str
    database: str
    config: ConnectionConfig            # .database set to this catalog
    backend_name: str
    is_default: bool
    connection_description: str
    database_description: str

class ResolvedTargets(BaseModel):
    targets: list[ResolvedTarget]
    default: ResolvedTarget
    file_default_connection: str
    # methods below

def resolve_targets(query_config: QueryFileConfig, db_config: DatabaseConfig) -> ResolvedTargets: ...
```
`ResolvedTargets` methods:
- `is_multi -> bool` (`len(targets) > 1`)
- `connection_names -> list[str]`, `database_names -> list[str]` (dedup, order)
- `get(connection, database) -> ResolvedTarget` (ValueError w/ available list)
- `for_connection(connection) -> list[ResolvedTarget]` (fan-out set)
- `resolve_pinned(connection: str | None, database: str | None) -> ResolvedTarget`
  (decision 15: connection→file default; database→connection's default_database)

Keep the existing `resolve_connection` for now (Step 6 migrates `server.py`,
Step 13 migrates `orchestrator.py` and then deletes `resolve_connection`).

## HOW
`resolve_targets` iterates `db_config.connections` in order, then each
connection's `databases` in order, building one `ResolvedTarget` per pair with
`config=conn.model_copy(update={"database": db.name})`. `default` = target for
`(query_config.connection, that connection's default_database)`. Reuse
`resolve_connection`'s "not found" error wording for the file-default connection.

## ALGORITHM (resolve_targets)
```
targets = []
for cname, conn in db_config.connections.items():
    for db in conn.databases:
        is_def = (cname == file_conn and db.name == conn.default_database)
        targets.append(ResolvedTarget(cname, db.name, conn.model_copy(database=db.name),
                                      conn.backend, is_def, conn.description, db.description))
default = next(t for t in targets if t.is_default)   # ValueError if file_conn unknown
return ResolvedTargets(targets, default, file_conn)
```

## DATA
`ResolvedTargets` is the single object threaded to every tool family and to
verify. Order is config order (connections × databases).

## TESTS (write first)
- single connection / single database → `is_multi is False`, one target, `default`
  set, both descriptions empty.
- two connections, one with two databases → target count, order, `database_names`
  union/dedup, `is_multi is True`.
- `get()` unknown connection/database → `ValueError` listing available.
- `resolve_pinned(None, None)` → default; `resolve_pinned("prod","hr")` → that
  target; `resolve_pinned("localdb","hr")` (hr not in localdb) → `ValueError`.
- unknown file-default connection → `ValueError`.

## LLM PROMPT
> Implement Step 4 from `pr_info/steps/step_4.md` (context in
> `pr_info/steps/summary.md`). Add frozen `ResolvedTarget` and `ResolvedTargets`
> (with `is_multi`, `connection_names`, `database_names`, `get`, `for_connection`,
> `resolve_pinned`) to `config/models.py`, and `resolve_targets` to
> `config/loader.py` building one target per `(connection, database)` via
> `model_copy`. Leave `resolve_connection` in place. Write the resolution tests
> first. Run pylint, pytest (`-n auto` + unit markers), mypy via MCP tools; all
> green. One commit.
