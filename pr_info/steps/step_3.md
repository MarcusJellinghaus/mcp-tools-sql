# Step 3 — Config models: multi-database fields

See `pr_info/steps/summary.md` → "Config shape".

## WHERE
- `src/mcp_tools_sql/config/models.py`
- Tests: `tests/config/test_models.py`

## WHAT
Add to `ConnectionConfig`:
```python
description: str = ""
databases: list[DatabaseSpec] = []      # internal normalised shape
default_database: str = ""
# `database: str = ""` stays as a legacy INPUT alias, normalised away
```
New model:
```python
class DatabaseSpec(BaseModel):
    name: str
    description: str = ""
```
Add optional pinned fields:
```python
class QueryConfig:  ...  connection: str = ""; database: str = ""
class UpdateConfig: ...  connection: str = ""; database: str = ""
```

## HOW
Two validators on `ConnectionConfig`:

`@model_validator(mode="before")` — normalise input into `databases`
(list[DatabaseSpec]) + `default_database`:
- sqlite → `databases=[{"name":"main"}]`, `default_database="main"` (ignore any
  authored `database`/`databases` for sqlite).
- list form `["sales","hr"]` → `[{"name":"sales"},{"name":"hr"}]`.
- table form `{"sales":{"description":...}}` → `[{"name":"sales","description":...}]`
  (preserve declared order).
- legacy `database="sales"` (and no `databases`) → `[{"name":"sales"}]`,
  `default_database="sales"`.
- `default_database` defaults to `databases[0].name` when unset.

`@model_validator(mode="after")` — validate:
- `default_database` is a member of `databases`.
- mssql: `databases` non-empty (≥1).
- postgresql: exactly one entry.
- legacy `database` set together with an explicit `databases` that disagrees →
  `ValueError` (rule 7).

## ALGORITHM (before-validator)
```
if backend == "sqlite": return {..., databases:[{name:"main"}], default_database:"main"}
raw = data.get("databases") or ([data["database"]] if data.get("database") else [])
specs = [ {name:x} if str else {name:k, **v} for x/k,v in raw ]
data["databases"] = specs
data.setdefault("default_database", specs[0]["name"] if specs else "")
return data
```

## DATA
`ConnectionConfig.databases: list[DatabaseSpec]`; `default_database: str`.
Backward compatible: existing single-`database` configs load unchanged.

## TESTS (write first, parameterised)
- list form, table form, legacy `database`, sqlite normalisation each produce the
  expected `databases` + `default_database`.
- `default_database` not in `databases` → `ValidationError`.
- postgresql with 2 databases → `ValidationError`; with 1 → ok.
- mssql with empty databases → `ValidationError`.
- legacy `database` conflicting with explicit `databases` → `ValidationError`.
- `QueryConfig`/`UpdateConfig` accept optional `connection`/`database`, default `""`.

## LLM PROMPT
> Implement Step 3 from `pr_info/steps/step_3.md` (context in
> `pr_info/steps/summary.md`). Add `DatabaseSpec`, extend `ConnectionConfig` with
> `description`/`databases`/`default_database` plus before/after validators that
> normalise the list form, table form, legacy `database`, and sqlite→`main`, and
> enforce the membership/per-backend/conflict rules. Add optional
> `connection`/`database` to `QueryConfig` and `UpdateConfig`. Write the
> parameterised model tests first. Keep existing single-`database` configs loading
> unchanged. Run pylint, pytest (`-n auto` + unit markers), mypy via MCP tools;
> all green. One commit.
