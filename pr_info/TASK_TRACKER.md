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

- [ ] [Step 1](./steps/step_1.md) — Keyword-absorption guard + reworded rejection message
- [ ] [Step 2](./steps/step_2.md) — Shared verdict helper + the registration gate
- [ ] [Step 3](./steps/step_3.md) — Switch the tool-facing read paths to `execute_readonly_query`
- [ ] [Step 4](./steps/step_4.md) — Stop truncating verify row labels
- [ ] [Step 5](./steps/step_5.md) — Per-variant `read_only` rows in `verify`
- [ ] [Step 6](./steps/step_6.md) — `:memory:` warning on the sqlite `path` row
- [ ] [Step 7](./steps/step_7.md) — Documentation

## Pull Request
