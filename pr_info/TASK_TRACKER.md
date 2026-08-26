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

- [x] [Step 1 — Backend read-only describe method](./steps/step_1.md)
- [x] [Step 2 — Move the leading-CTE gate to `utils`](./steps/step_2.md)
- [ ] [Step 3 — `summarize/source.py`: validate + probe](./steps/step_3.md)
- [ ] [Step 4 — Refactor the table path onto `Source`](./steps/step_4.md)
- [ ] [Step 5 — Wire the `sql=` parameter end to end](./steps/step_5.md)
- [ ] [Step 6 — T-SQL DMF resolver with probe fallback](./steps/step_6.md) — conditional on the prerequisite in the step file

## Pull Request
