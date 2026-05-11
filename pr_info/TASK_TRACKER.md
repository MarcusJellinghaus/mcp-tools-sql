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

- [x] [Step 1 — Add `truncation_hint` parameter to `format_rows`](steps/step_1.md)
- [x] [Step 2 — Rename `max_rows` → `max_rows_default`; add `max_rows_hard` clamp](steps/step_2.md)
- [ ] [Step 3 — Create `tool_builder.py`; extract helpers; add layer](steps/step_3.md)
- [ ] [Step 4 — Add `filter_column`; auto-inject `max_rows` and `<col>_filter` params](steps/step_4.md)
- [ ] [Step 5 — Convert `register_builtin_tools` to `SchemaTools` class](steps/step_5.md)
- [ ] [Step 6 — Implement `QueryTools` class; wire into `server.py`](steps/step_6.md)

## Pull Request
