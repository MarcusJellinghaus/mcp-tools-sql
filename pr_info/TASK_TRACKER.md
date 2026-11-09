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

### Step 1: Move `utils/sql_placeholders.py` → `sql_ast/placeholders.py` — [step_1.md](./steps/step_1.md)
- [x] Implementation (tests + production code)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 2: Move `summarize/sql.py` → `sql_ast/summarize_queries.py`; split the readonly test — [step_2.md](./steps/step_2.md)
- [x] Implementation (tests + production code)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 3: `SqlParseError` and one translation decorator — [step_3.md](./steps/step_3.md)
- [x] Implementation (tests + production code)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 4: Opaque `SourceRef` / `Predicate`; `summarize/source.py` sqlglot-free — [step_4.md](./steps/step_4.md)
- [x] Implementation (tests + production code)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 5: Neutral backend exceptions; upper layers catch them (additively) — [step_5.md](./steps/step_5.md)
- [ ] Implementation (tests + production code)
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

### Step 6: SQLite backend translates driver errors — [step_6.md](./steps/step_6.md)
- [ ] Implementation (tests + production code)
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

### Step 7: MSSQL backend translates driver errors — [step_7.md](./steps/step_7.md)
- [ ] Implementation (tests + production code)
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

### Step 8: SHOWPLAN into `MSSQLBackend.explain(isolated=True)`; drop `get_isolated_connection` — [step_8.md](./steps/step_8.md)
- [ ] Implementation (tests + production code)
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

### Step 9: Upper layers drop raw driver exception types — [step_9.md](./steps/step_9.md)
- [ ] Implementation (tests + production code)
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

### Step 10: Dependency probes in the backends — [step_10.md](./steps/step_10.md)
- [ ] Implementation (tests + production code)
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

### Step 11: `tests/sqlite_fixtures.py`; non-owner tests off `sqlite3` and `sqlglot` — [step_11.md](./steps/step_11.md)
- [ ] Implementation (tests + production code)
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

### Step 12: Isolation contracts, canary, docs — [step_12.md](./steps/step_12.md)
- [ ] Implementation (tests + production code)
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

## Pull Request
- [ ] PR review: review full branch diff against `main`, address findings
- [ ] PR summary prepared
