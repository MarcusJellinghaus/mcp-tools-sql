# Issue #4: Schema Introspection MCP Tools (Config-Driven)

## Overview

Replace hardcoded introspection methods on the backend ABC with **config-driven SQL queries** defined in `default_queries.toml`. Each query entry becomes an MCP tool at server startup via dynamic function registration. This builds the foundation pipeline that issue #5 will reuse for user-defined SELECT tools.

## Architectural / Design Changes

### Before (current)
- `DatabaseBackend` ABC has 4 introspection methods: `read_schemas()`, `read_tables()`, `read_columns()`, `read_relations()`
- Each backend (SQLite, MSSQL) implements these methods with hardcoded SQL
- `SchemaTools` class wraps a backend and registers tools (stub, not implemented)
- `formatting.py` has stubs for `format_rows()`, `format_columns()`, `format_update_result()`

### After (target)
- `DatabaseBackend` ABC slimmed to execution primitives only: `connect()`, `close()`, `execute_query()`, `execute_update()`, `explain()`, context manager
- `QueryConfig` gains per-backend SQL override via `BackendQueryConfig` model and `resolve_sql()` method
- 4 schema tools defined in `default_queries.toml` with default SQL (INFORMATION_SCHEMA) + SQLite overrides
- `schema_tools.py` contains plain functions (no class) that build dynamic tool functions and register them on FastMCP
- Param stripping: resolved SQL scanned for `:param` references, only matching params passed to `execute_query()`
- `format_rows()` implemented with `tabulate`, truncation at `max_rows`, LLM-friendly text output
- `server.py` creates `FastMCP` instance and wires builtin tool registration

### Key design decisions (from issue)
| Decision | Rationale |
|----------|-----------|
| Config-driven introspection | Unifies schema tools and future user-defined tools into one pipeline |
| Per-backend SQL in TOML | `sql` (default) + `[queries.X.backends.Y]` nested sections |
| Normalize in SQL via aliases | Each backend's SQL aliases columns to consistent names |
| `filter` applied in Python | `fnmatch` post-query, avoids per-backend WHERE variations |
| `max_rows` default 100 | Tool parameter, LLMs can override per-call |
| Param stripping | Scan SQL for `:param`, drop unused — keeps tool signature stable across backends |
| `schema` param on SQLite | Accepted as no-op, silently ignored for consistent interface |

## Files Modified

| File | Change |
|------|--------|
| `src/mcp_tools_sql/config/models.py` | Add `BackendQueryConfig`, extend `QueryConfig` with `backends` + `resolve_sql()` |
| `src/mcp_tools_sql/backends/base.py` | Remove 4 introspection methods from ABC |
| `src/mcp_tools_sql/backends/sqlite.py` | Remove 4 introspection methods |
| `src/mcp_tools_sql/backends/mssql.py` | Remove 4 introspection methods |
| `src/mcp_tools_sql/formatting.py` | Implement `format_rows()` with tabulate |
| `src/mcp_tools_sql/schema_tools.py` | Rewrite: plain functions for config-driven tool registration |
| `src/mcp_tools_sql/server.py` | Create FastMCP, wire `_register_builtin_tools()`, implement `run()` |
| `pyproject.toml` | Package-data for `*.toml` |
| `tests/config/test_models.py` | Tests for `BackendQueryConfig`, `resolve_sql()` |
| `tests/backends/test_sqlite.py` | Remove introspection tests, update `_DATA_METHODS` |
| `tests/conftest.py` | Add wide-table fixture for truncation tests |

## Files Created

| File | Purpose |
|------|---------|
| `src/mcp_tools_sql/default_queries.toml` | 4 schema queries with per-backend SQL overrides |
| `tests/test_formatting.py` | Tests for `format_rows()` |
| `tests/test_schema_tools.py` | Integration tests: tool registration, MCP protocol, SQLite end-to-end |

## Steps

1. **Config model + Backend ABC** — `BackendQueryConfig` model, `resolve_sql()`, remove introspection from ABC/backends, update tests
2. **`default_queries.toml` + package data** — Create TOML with 4 queries, configure packaging, verify SQLite pragma binding
3. **`format_rows()` implementation** — Tabulate formatting, truncation, empty results
4. **Tool registration pipeline + server wiring** — Dynamic function builder, param stripping, filter, server integration
5. **Integration tests** — MCP protocol tests, SQLite end-to-end, truncation, edge cases
