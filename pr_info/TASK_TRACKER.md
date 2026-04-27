# Task Status Tracker

## Instructions for LLM

This tracks **Feature Implementation** consisting of multiple **Tasks**.

**Summary:** See [summary.md](./steps/summary.md) for implementation overview.

**How to update tasks:**
1. Change [ ] to [x] when implementation step is fully complete (code + checks pass)
2. Change [x] to [ ] if task needs to be reopened
3. Add brief notes in the linked detail files if needed
4. Keep it simple - just GitHub-style checkboxes

**Task format:**
- [x] = Task complete (code + all checks pass)
- [ ] = Task not complete
- Each task links to a detail file in steps/ folder

---

## Tasks

- [x] [Step 1: Config model + Backend ABC](./steps/step_1.md) — `BackendQueryConfig`, `resolve_sql()`, remove introspection from ABC/backends
- [x] [Step 2: `default_queries.toml` + package data](./steps/step_2.md) — TOML with 4 queries, SQLite overrides, loader, pragma verification
- [x] [Step 3: `format_rows()` implementation](./steps/step_3.md) — Tabulate formatting, truncation, empty results
- [x] [Step 4: Tool registration pipeline + server wiring](./steps/step_4.md) — Dynamic function builder, param stripping, filter, FastMCP server
- [x] [Step 5: Integration tests](./steps/step_5.md) — MCP protocol tests, SQLite end-to-end, truncation, edge cases

## Pull Request
