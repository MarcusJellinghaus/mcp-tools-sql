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

### Step 1: UpdateConfig Schema Alias + Model Tests
> [step_1.md](./steps/step_1.md) — Add `Field(alias="schema")` to `UpdateConfig.schema_name`, write model validation tests.

- [x] Implementation: tests in `tests/config/test_models.py` + model change in `config/models.py`
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 2: TOML Loaders — load_query_config + load_user_config
> [step_2.md](./steps/step_2.md) — Implement TOML file loading, credential warnings, Pydantic validation.

- [x] Implementation: tests in `tests/config/test_loader.py` + loaders in `config/loader.py`
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 3: resolve_connection + discover_query_config
> [step_3.md](./steps/step_3.md) — Connection dict lookup and config file discovery chain.

- [x] Implementation: tests in `tests/config/test_loader.py` + functions in `config/loader.py`
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

## Pull Request

- [ ] PR review: all steps complete, tests pass, no regressions
- [ ] PR summary prepared
