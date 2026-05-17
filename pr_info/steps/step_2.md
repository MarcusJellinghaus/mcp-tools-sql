# Step 2 — Storage + listing helpers

**Prompt for LLM:**
> Read `pr_info/steps/summary.md` and then implement `pr_info/steps/step_2.md`.
> Step 1 is already merged — the builders exist. TDD: write the new tests
> first, run them red, then implement the storage/listing helpers, run them
> green. Finish by running pylint, mypy, ruff, tach, and import-linter — all
> must be clean. One commit.

---

## WHERE

- **Modify (impl):** `src/mcp_tools_sql/config/authoring.py` — append the new
  public functions below the Step 1 builders.
- **Modify (tests):** append to `tests/config/test_authoring.py`.

## WHAT

Public functions:

```python
def add_query(
    doc: tomlkit.TOMLDocument,
    name: str,
    qcfg: QueryConfig,
    *,
    include_defaults: bool = False,
) -> None: ...

def add_update(
    doc: tomlkit.TOMLDocument,
    name: str,
    ucfg: UpdateConfig,
    *,
    include_defaults: bool = False,
) -> None: ...

def remove_query(doc: tomlkit.TOMLDocument, name: str) -> None: ...
def remove_update(doc: tomlkit.TOMLDocument, name: str) -> None: ...

def list_configured_tools(
    doc: tomlkit.TOMLDocument,
) -> dict[str, list[str]]: ...
```

Plus two private shared helpers (KISS — one logic path per direction):

```python
def _add_entry(
    doc: tomlkit.TOMLDocument,
    parent_key: str,        # "queries" or "updates"
    name: str,
    payload: dict[str, Any],
) -> None: ...

def _remove_entry(
    doc: tomlkit.TOMLDocument,
    parent_key: str,
    name: str,
) -> None: ...
```

## HOW

- Imports: `tomlkit`, plus the pydantic models already imported in Step 1.
- All mutations are in place on the supplied `TOMLDocument`. File I/O is the
  caller's problem.
- `add_*` raises `ValueError` on duplicate name; the parent `[queries]` or
  `[updates]` table is auto-created when absent.
- `remove_*` raises `KeyError` on missing name **or** missing parent section;
  if the removal empties the parent table, the parent table is deleted too.
- `list_configured_tools` returns `{"queries": [...], "updates": [...]}` —
  missing sections become empty lists (silent valid empty).

## ALGORITHM

`add_query(doc, name, qcfg, *, include_defaults)`:
```
payload = qcfg.model_dump(by_alias=True, exclude_defaults=not include_defaults)
if not include_defaults and payload.get("max_rows_hard") == qcfg.max_rows_default:
    payload.pop("max_rows_hard", None)
_add_entry(doc, "queries", name, payload)
```

`add_update(doc, name, ucfg, *, include_defaults)`:
```
payload = ucfg.model_dump(by_alias=True, exclude_defaults=not include_defaults)
_add_entry(doc, "updates", name, payload)
```

`_add_entry(doc, parent_key, name, payload)`:
```
parent = doc.get(parent_key)
if parent is None:
    parent = tomlkit.table()
    doc[parent_key] = parent
if name in parent:
    raise ValueError(f"{parent_key}.{name} already exists")
entry = tomlkit.table()

# Pass 1 — scalars / non-dict, non-list values first (must precede any
# sub-table header).
for k, v in payload.items():
    if isinstance(v, dict):
        continue
    if isinstance(v, list):
        continue
    entry[k] = v                                    # scalar → tomlkit handles it

# Pass 2 — dict-valued payload items as sub-tables
# (rendered as [<parent>.<n>.<k>] headers). Recurse into nested dicts so
# each inner dict also becomes a proper sub-table header rather than an
# inline table.
for k, v in payload.items():
    if not isinstance(v, dict):
        continue
    sub = tomlkit.table()
    for ik, iv in v.items():
        # If the inner value is itself a dict (e.g. params = {"id": {...}}),
        # wrap recursively so it renders as [<parent>.<n>.<k>.<ik>] and not
        # as `<ik> = {...}` inline.
        sub[ik] = _to_toml_table(iv) if isinstance(iv, dict) else iv
    entry[k] = sub

# Pass 3 — list-valued payload items as Arrays of Tables
# (rendered as [[<parent>.<n>.<k>]] blocks, e.g. updates.<n>.fields).
# Today's AoT-element model shape (UpdateFieldConfig) is flat: every
# field is a scalar, so a single-level loop suffices. If a future model
# introduces nested dicts inside an AoT element, reuse `_to_toml_table`
# here for the same reason as Pass 2.
for k, v in payload.items():
    if not isinstance(v, list):
        continue
    aot = tomlkit.aot()
    for item in v:
        sub = tomlkit.table()
        for ik, iv in item.items():
            sub[ik] = iv
        aot.append(sub)
    entry[k] = aot

parent[name] = entry
```

Small recursive helper used by Pass 2 (and available for future AoT
nesting):

```
def _to_toml_table(d: dict) -> tomlkit.items.Table:
    t = tomlkit.table()
    for k, v in d.items():
        t[k] = _to_toml_table(v) if isinstance(v, dict) else v
    return t
```

Concretely: `QueryConfig.params` round-trips as
`{"id": {"type": "int", "required": True}}` out of `model_dump`. Pass 2
wraps the OUTER `params` dict in `tomlkit.table()`, but its inner value
`{"type": "int", "required": True}` is itself a dict — assigning it
directly would render as `params.id = {type = "int", required = true}`
(inline), not as the documented `[queries.<n>.params.id]` sub-table.
`_to_toml_table` makes the recursion explicit so each nested dict layer
becomes its own sub-table header.

Why three passes instead of a single in-order loop: pydantic emits fields
in declaration order, so naive iteration would place sub-tables before
later scalars. Once a `[a.b.c]` header appears in TOML, every following
key-value belongs to that table — so we must emit all scalars first, then
nested structures. Concretely for `QueryConfig` the declaration order is
`description, sql, params, max_rows_default, max_rows_hard, filter_column,
backends`; emitting `params` (a dict → sub-table) before
`max_rows_default` (a scalar) would silently re-parent
`max_rows_default = 1` under `[queries.<n>.params.<key>]` on round-trip.

Why the explicit `tomlkit.table()` wrap for nested dicts: assigning a raw
Python `dict` to a tomlkit `Table` renders it as an **inline** table
(`key = {field = "id", ...}`), which would break the documented
`[updates.<n>.key]` sub-table header requirement and the
`[queries.<n>.params.<key>]` sub-table layout. Wrapping in
`tomlkit.table()` (mirroring the `fields` AoT branch) forces a proper
sub-table header.

`_remove_entry(doc, parent_key, name)`:
```
parent = doc.get(parent_key)
if parent is None or name not in parent:
    raise KeyError(f"{parent_key}.{name}")
del parent[name]
if len(parent) == 0:
    del doc[parent_key]
```

`list_configured_tools(doc)`:
```
queries = doc.get("queries") or {}
updates = doc.get("updates") or {}
return {"queries": list(queries.keys()), "updates": list(updates.keys())}
```

## DATA

- `add_*` / `remove_*` return `None`; their effect is the mutation of `doc`.
- `list_configured_tools` returns `dict[str, list[str]]` with keys exactly
  `"queries"` and `"updates"`.

## Tests (parametrize where noted)

Append to `tests/config/test_authoring.py`:

1. **`add_query` happy path round-trip.** Build via `build_query_config`, add
   to empty doc, `tomlkit.dumps` → `tomllib.loads` → reconstruct
   `QueryConfig`, assert equal to original.
1a. **`add_query` key order — scalars before sub-tables.** Build a query
    with both `max_rows_default=1` AND `params={"id": {"type": "int",
    "required": True}}`. After `add_query` + `tomlkit.dumps(doc)`, assert
    `dumped.index("max_rows_default") < dumped.index("[queries.")` — i.e.
    the `max_rows_default = 1` line appears BEFORE the
    `[queries.<n>.params.id]` section header. Guards the TOML
    header-scoping bug: if a scalar follows a sub-table header it gets
    silently re-parented under that sub-table on round-trip.
2. **`add_query` lean output suppresses defaults.** Build with no
   `filter_column`, `max_rows_hard=None`, empty `description`, no `backends`.
   After `add_query` (default `include_defaults=False`) and `tomlkit.dumps`:
   asserted TOML does NOT contain the keys `max_rows_hard`, `filter_column`,
   `backends`, `description`.
3. **`add_query` with `include_defaults=True`** emits all of the above keys.
4. **Parametrize: `add_query` with zero / one / multiple params.**
   - 0: `params` section absent from emitted TOML.
   - 1: single `[queries.<n>.params.<key>]` sub-table.
   - 3: three sub-tables in insertion order.
5. **`add_query` rejects duplicate name** with `ValueError`.
6. **`add_query` creates `[queries]` section when absent** (fresh empty doc).
7. **`add_update` happy path round-trip** with key + 2 fields. Assert AoT
   structure (parsed `fields` is `list[dict]`, not inline `[{...},{...}]`).
   Pragmatic check: re-parsed `UpdateConfig` equals built one.
7a. **`add_update` emits `key` as a sub-table, not inline.** After
    `add_update(...)` for `set_user_email`, assert the rendered
    `tomlkit.dumps(doc)` string contains the literal section header
    `[updates.set_user_email.key]` AND does NOT contain `key = {`
    (guards against the inline-table regression).
8. **`add_update` rejects duplicate name** with `ValueError`.
9. **Parametrize: `remove_query` / `remove_update` happy path** then
   re-`list_configured_tools` shows it gone.
10. **Parametrize: `remove_*` raises `KeyError` on missing name AND on
    missing section** (matrix: 2 functions × 2 conditions = 4 cases).
11. **`remove_*` prunes empty parent.** Add one entry, remove it, assert
    `"queries"` / `"updates"` key is no longer in the doc (`"queries" not in doc`).
    Robustness: also round-trip the post-removal doc through
    `tomlkit.dumps(doc)` + `tomllib.loads(...)` and assert the top-level
    `"queries"` / `"updates"` key is absent from the parsed mapping
    (catches any tomlkit trivia retention that re-materialises the section).
12. **Parametrize: `list_configured_tools` four cases** (empty / queries
    only / updates only / both). Empty doc returns `{"queries": [], "updates": []}`.

Run gates: same as Step 1.
