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

### Step 1: Schema constraint — `max_rows` must be `>= 1` ([step_1.md](./steps/step_1.md))

- [ ] Implementation: `Field(ge=1)` on the `max_rows` annotation in `build_query_sig_params`; schema `minimum` assertion plus MCP-level rejection test in `tests/test_query_tools.py`
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared: `fix(query): reject max_rows below 1 at the tool schema`

### Step 2: Lower clamp in `_cap_max_rows` ([step_2.md](./steps/step_2.md))

- [ ] Implementation: floor both `requested` and `hard` at 1 in `_cap_max_rows` plus docstring update; direct unit test in `tests/test_query_tools.py`
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared: `fix(query): floor max_rows and max_rows_hard at 1 in the cap helper`

### Step 3: Floor at the two formatting sinks ([step_3.md](./steps/step_3.md))

- [ ] Implementation: `max_rows = max(max_rows, 1)` in `format_rows` and `format_fanout_rows` plus docstring notes; negative-`max_rows` tests for both in `tests/test_formatting.py`
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared: `fix(formatting): floor max_rows at 1 in the row and fan-out renderers`

### Step 4: `verify` reports `max_rows_hard <= 0` ([step_4.md](./steps/step_4.md))

- [ ] Implementation: `_positive_entry` helper and `<name>.max_rows_hard` row in `verification/queries.py`; test in `tests/verification/test_queries.py`; `tests/cli/fixtures/verify_snapshot.txt` and `docs/cli.md` updates
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared: `feat(verify): check max_rows_hard > 0 alongside max_rows_default`

## Pull Request

- [ ] Code review of the full branch diff — fix all findings
- [ ] PR summary written
