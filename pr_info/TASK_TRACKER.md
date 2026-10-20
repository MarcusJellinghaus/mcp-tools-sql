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

<!-- Tasks populated from pr_info/steps/ by prepare_task_tracker -->

### Step 1: Split tool registration from the stdio transport in `server.py`
- [x] Implementation (tests + production code)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 2: `tool` subcommand skeleton — discovery surface
- [x] Implementation (tests + production code)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 3: dynamic per-tool argument parser (`tool_args.py`)
- [x] Implementation (tests + production code)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

### Step 4: exit-code classifier and dispatch wrapper (`tool_dispatch.py`)
- [ ] Implementation (tests + production code)
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

### Step 5: wire argument parsing and dispatch into `tool.py` — full invocation
- [ ] Implementation (tests + production code)
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

### Step 6: documentation
- [ ] Implementation (docs only — no tests)
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

## Pull Request

- [ ] Review full diff across all steps
- [ ] PR summary written
