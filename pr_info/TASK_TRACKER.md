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

### Step 1: Relocate `to_dialect` to `backends/base.py` and make it strict

See [step_1.md](./steps/step_1.md).

- [x] Implementation: add `_DIALECTS` + strict `to_dialect` to `backends/base.py`, update `create_backend`'s enumerated message, remove `to_dialect` from `utils/sql_placeholders.py` (`__all__` + docstring), move the three call-site imports, add `to_dialect` unit tests in `tests/test_smoke.py`, update `test_connection.py` fixture literal
- [x] Quality checks: pylint, pytest, mypy (also lint-imports, ruff) — fix all issues
- [x] Commit message prepared

### Step 2: Dialect-first parse-error verdict in `basic_preflight`

See [step_2.md](./steps/step_2.md).

- [x] Implementation: change `basic_preflight`'s `ParseError` verdict to the dialect-first f-string, update the four parse-error assertions in the test suite
- [x] Quality checks: pylint, pytest, mypy (also ruff) — fix all issues
- [x] Commit message prepared

### Step 3: Bump the sqlglot floor to `>=30`

See [step_3.md](./steps/step_3.md).

- [ ] Implementation: change `"sqlglot>=25"` to `"sqlglot>=30"` in `pyproject.toml` (no upper bound), confirm existing suite stays green
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

## Pull Request

- [ ] Address PR review feedback
- [ ] Write PR summary
