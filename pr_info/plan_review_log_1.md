# Plan Review Log — Run 1

**Issue:** #4 — Schema Introspection MCP Tools (Config-Driven)
**Branch:** 4-schema-introspection-mcp-tools-config-driven
**Date:** 2026-04-26

## Round 1 — 2026-04-26

**Findings:**
- F1 (Critical): `read_columns` default SQL uses MySQL-specific `COLUMN_KEY` — doesn't exist on MSSQL
- F2 (Critical): `read_relations` default SQL uses MySQL-specific `REFERENCED_TABLE_NAME`/`REFERENCED_COLUMN_NAME`
- F4 (Critical): `max_rows` exists as both `QueryConfig.max_rows` and `params.max_rows` — interaction unclear
- F6 (Accept): Pragma fallback strategy suggests positional binding but `execute_query` uses dict params
- F8 (Accept): `backend_name: str = "sqlite"` default in ToolServer is misleading
- F13 (Accept): Test `test_read_columns_has_max_rows_param` claims to check "default 100" but QueryParamConfig has no default field
- F3,5,7,9,10,11,12,14,15 (Skip): Confirmed consistent, cosmetic, or speculative

**Decisions:**
- F1+F2: Accept — rewrite default SQL to target MSSQL INFORMATION_SCHEMA with JOINs (user chose option A)
- F4: Accept — clarify in step 4 that `config.max_rows` provides the default value
- F6: Accept — update fallback to table-valued function syntax
- F8: Accept — remove default, pass from `ConnectionConfig.backend`
- F13: Accept — clarify test checks param exists + `config.max_rows == 100` separately
- All others: Skip

**User decisions:**
- Q: How to handle MySQL-specific default SQL? Options: (A) target MSSQL, (B) add MSSQL overrides, (C) defer with TODO
- A: Option A — write default SQL targeting MSSQL's INFORMATION_SCHEMA

**Changes:**
- `step_2.md`: Rewrote `read_columns` and `read_relations` default SQL with MSSQL-compatible JOINs; updated pragma fallback strategy; clarified test description
- `step_4.md`: Clarified `max_rows` default interaction; removed `backend_name` default

**Status:** committed

## Round 2 — 2026-04-26

**Findings:**
- F1 (Critical): `read_columns` default SQL still used MySQL `COLUMN_KEY` — round 1 fix was applied to `read_relations` but missed `read_columns`
- F2 (Accept): `read_relations` SQL confirmed correct after round 1 fix
- F3 (Accept): `backend_name` text slightly confusing but final resolution is clear
- F4 (Skip): Pragma note slightly stale but SQL itself is correct

**Decisions:**
- F1: Accept — apply the MSSQL-compatible JOIN for `read_columns`
- F2, F3: No changes needed
- F4: Skip

**User decisions:** None needed

**Changes:**
- `step_2.md`: Replaced `read_columns` default SQL with MSSQL-compatible JOIN to `TABLE_CONSTRAINTS` + `KEY_COLUMN_USAGE` for PK detection

**Status:** committed

