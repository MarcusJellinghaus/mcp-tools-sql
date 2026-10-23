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

### Step 1: Move `create_backend` into `backends/registry.py` (fix R0401 cycle) — [step_1.md](./steps/step_1.md)
- [ ] Implementation: update test imports, move `create_backend` to `registry.py`, update comments/docstrings
- [ ] Quality checks: pylint (incl. `--enable=R0401`), pytest, mypy — fix all issues
- [ ] Commit message prepared

### Step 2: Full pylint run with mcp_coder's config — [step_2.md](./steps/step_2.md)
- [ ] Implementation: pylint config in `pyproject.toml`, fix W1404 and W0223 findings, CI full pylint run
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

### Step 3: pytest `addopts` aligned with mcp_coder — [step_3.md](./steps/step_3.md)
- [ ] Implementation: update `addopts` in `pyproject.toml`, drop `-n auto` from CI pytest command
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

### Step 4: CI installs GitHub deps from `[tool.mcp-coder.install-from-github]` — [step_4.md](./steps/step_4.md)
- [ ] Implementation: port `tools/read_github_deps.py`, replace hardcoded git URL installs in workflows with `--specs`
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

### Step 5: `subprocess_runner` shim + import-health test — [step_5.md](./steps/step_5.md)
- [ ] Implementation: port `tests/test_module_imports.py` and `tests/_import_walker.py`, add `utils/subprocess_runner.py` shim
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

### Step 6: Upstream compat check workflow — [step_6.md](./steps/step_6.md)
- [ ] Implementation: move `upstream-mypy-check.yml` to `upstream-compat-check.yml`, add strict import step
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

### Step 7: Enforce the `mcp_coder_utils` shim boundary with import-linter — [step_7.md](./steps/step_7.md)
- [ ] Implementation: add `mcp_coder_utils_isolation` contract to `.importlinter`, update CLAUDE.md "Shared Libraries"
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

### Step 8: Local check scripts; CI architecture jobs call them — [step_8.md](./steps/step_8.md)
- [ ] Implementation: copy 10 `tools/*.sh`/`.bat` scripts from mcp_coder, set exec bit on CI-invoked `.sh`, update CI architecture matrix
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

### Step 9: black and isort CI cover `tools/` — [step_9.md](./steps/step_9.md)
- [ ] Implementation: extend black and isort CI commands to `src tests tools`
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

## Pull Request
- [ ] PR review: review full branch diff against `main`, address findings
- [ ] PR summary prepared
