# Issue #2: Config — Pydantic Models and TOML Loader

## Summary

Implement TOML config loading and validation for the two-file config architecture:
- **Query config** (`mcp-tools-sql.toml`) — project-level, defines queries/updates + a named connection reference
- **User config** (`~/.mcp-tools-sql/config.toml`) — per-machine, holds database connections with credentials

The models in `config/models.py` already exist and need a minor refinement (schema alias). The loader in `config/loader.py` has stub signatures that need real implementations.

## Design Changes

### Model change (`config/models.py`)

`UpdateConfig.schema_name` gets `Field(alias="schema")` so TOML uses `schema = "dbo"` while Python uses `schema_name`. Requires `model_config = ConfigDict(populate_by_name=True)` on `UpdateConfig` only.

### Loader implementation (`config/loader.py`)

Four public functions replace the current stubs:

| Function | Responsibility |
|---|---|
| `load_query_config(path)` | Read TOML, warn on credentials in wrong file, validate with Pydantic |
| `load_user_config(path)` | Load from path or default `~/.mcp-tools-sql/config.toml`, return defaults if missing |
| `resolve_connection(query_config, user_config)` | Dict lookup of connection name — not a merge |
| `discover_query_config(config_flag, project_dir)` | CLI flag → project dir file → error |

Error handling: `TOMLDecodeError` and `OSError` wrapped in `ValueError` with file path context. No custom exception classes. Credential warning scans raw TOML dict before Pydantic parsing (Pydantic silently drops extra fields, so post-parse detection is impossible).

### No architectural changes

- Layer constraints unchanged — `config/` depends only on `utils` and stdlib
- No new dependencies — uses `tomllib` (stdlib Python 3.11+)
- No re-exports in `config/__init__.py`

## Files Modified

| File | Change |
|---|---|
| `src/mcp_tools_sql/config/models.py` | Add `Field(alias=...)` + `ConfigDict` to `UpdateConfig` |
| `src/mcp_tools_sql/config/loader.py` | Replace stubs with full implementations |
| `tests/test_config.py` | **New** — all config tests (models + loader) |

## Implementation Steps

| Step | Scope | Commit |
|---|---|---|
| 1 | `UpdateConfig` schema alias + model tests | Tests + 2-line model change |
| 2 | `load_query_config` + `load_user_config` + loader tests | Tests + TOML loading implementation |
| 3 | `resolve_connection` + `discover_query_config` + tests | Tests + resolution/discovery logic |
