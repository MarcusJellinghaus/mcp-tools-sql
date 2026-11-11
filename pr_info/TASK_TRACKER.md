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

### Step 1: Backend names — supported set and `pyodbc` alias
[Detail](./steps/step_1.md)

- [x] Implementation (tests + production code)
- [x] Quality checks — fix all issues
- [x] Commit message prepared

### Step 2: Per-connection dependency check; DEPENDENCIES per connection; remove psycopg probe
[Detail](./steps/step_2.md)

- [x] Implementation (tests + production code)
- [x] Quality checks — fix all issues
- [x] Commit message prepared

### Step 3: `load_database_config` — explicit missing path raises
[Detail](./steps/step_3.md)

- [x] Implementation (tests + production code)
- [x] Quality checks — fix all issues
- [x] Commit message prepared

### Step 4: `build_toolset` fails early on dependency errors
[Detail](./steps/step_4.md)

- [x] Implementation (tests + production code)
- [x] Quality checks — fix all issues
- [x] Commit message prepared

### Step 5: Config-only section parameters (CONNECTION `connect`, QUERIES `registry=None`)
[Detail](./steps/step_5.md)

- [ ] Implementation (tests + production code)
- [ ] Quality checks — fix all issues
- [ ] Commit message prepared

### Step 6: Orchestrator — shared head and `collect_sections` with `toolset.build` row
[Detail](./steps/step_6.md)

- [ ] Implementation (tests + production code)
- [ ] Quality checks — fix all issues
- [ ] Commit message prepared

### Step 7: Public `toolset.verify` and the `utils/<home>.py` shim
[Detail](./steps/step_7.md)

- [ ] Implementation (tests + production code)
- [ ] Quality checks — fix all issues
- [ ] Commit message prepared

### Step 8: Docs
[Detail](./steps/step_8.md)

- [ ] Implementation (docs updates)
- [ ] Quality checks — fix all issues
- [ ] Commit message prepared

## Pull Request

- [ ] PR review — review the full branch diff against the base branch and address findings
- [ ] PR summary prepared
