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

### Step 1: deptry — config, dependency cleanup, check script, CI job ([step_1.md](./steps/step_1.md))
- [x] Implementation (pyproject.toml, tools/deptry_check.sh/.bat, ci.yml; `deptry src` clean)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 2: Coverage summary script + ported tests, dev deps, .gitignore, ruff ignore ([step_2.md](./steps/step_2.md))
- [x] Implementation (tests + production code)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 3: CI coverage wiring — unit-tests job, --cov on integration jobs, uploads, coverage job ([step_3.md](./steps/step_3.md))
- [x] Implementation (tests + production code)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

## Pull Request
- [ ] PR review: review all changes against the issue's acceptance criteria
- [ ] PR summary prepared
