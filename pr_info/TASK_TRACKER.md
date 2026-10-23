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
- [x] Implementation: update test imports, move `create_backend` to `registry.py`, update comments/docstrings
- [x] Quality checks: pylint (incl. `--enable=R0401`), pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 2: Full pylint run with mcp_coder's config — [step_2.md](./steps/step_2.md)
- [x] Implementation: pylint config in `pyproject.toml`, fix W1404 and W0223 findings, CI full pylint run
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 3: pytest `addopts` aligned with mcp_coder — [step_3.md](./steps/step_3.md)
- [x] Implementation: update `addopts` in `pyproject.toml`, drop `-n auto` from CI pytest command
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 4: CI installs GitHub deps from `[tool.mcp-coder.install-from-github]` — [step_4.md](./steps/step_4.md)
- [x] Implementation: port `tools/read_github_deps.py`, replace hardcoded git URL installs in workflows with `--specs`
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 5: `subprocess_runner` shim + import-health test — [step_5.md](./steps/step_5.md)
- [x] Implementation: port `tests/test_module_imports.py` and `tests/_import_walker.py`, add `utils/subprocess_runner.py` shim
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 6: Upstream compat check workflow — [step_6.md](./steps/step_6.md)
- [x] Implementation: move `upstream-mypy-check.yml` to `upstream-compat-check.yml`, add strict import step
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 7: Enforce the `mcp_coder_utils` shim boundary with import-linter — [step_7.md](./steps/step_7.md)
- [x] Implementation: add `mcp_coder_utils_isolation` contract to `.importlinter`, update CLAUDE.md "Shared Libraries"
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 8: Local check scripts; CI architecture jobs call them — [step_8.md](./steps/step_8.md)
- [x] Implementation: copy 10 `tools/*.sh`/`.bat` scripts from mcp_coder, set exec bit on CI-invoked `.sh`, update CI architecture matrix
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 9: black and isort CI cover `tools/` — [step_9.md](./steps/step_9.md)
- [x] Implementation: extend black and isort CI commands to `src tests tools`
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

## Pull Request
- [ ] PR review: review full branch diff against `main`, address findings
- [ ] PR summary prepared
