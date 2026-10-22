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

### Step 1: Gate preview rules behind `explicit-preview-rules` — [step_1.md](./steps/step_1.md)

- [x] Implementation: `pyproject.toml` gate + exact DOC codes; DOC501 `.scratch/` probe confirms DOC still enforces, then delete `.scratch/`
- [x] Quality checks: ruff, pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 2: Enable already-clean groups (F, E, C4, ANN, SIM, SIM905, PLW1510) — [step_2.md](./steps/step_2.md)

- [x] Implementation: extend `select`/`ignore`, tests per-file ignore adds `SIM117`
- [x] Quality checks: ruff, pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 3: Enable `B` and fix bugbear findings — [step_3.md](./steps/step_3.md)

- [x] Implementation: `B017` narrowed `pytest.raises`, `B905` `zip(strict=True)`, `B009` plain attribute access
- [x] Quality checks: ruff, pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 4: Replace backend connection asserts with explicit `RuntimeError` — [step_4.md](./steps/step_4.md)

- [x] Implementation: `SQLiteBackend._require_connection()` + 4 callers; MSSQL `_ensure_connected` assert → raise with `Raises:` docstring
- [x] Quality checks: ruff, pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 5: Replace asserts in `update_tools` and `summarize` — [step_5.md](./steps/step_5.md)

- [x] Implementation: builders raise `ValueError` with `Raises:` docstrings; summarize condition tests `distinct is not None`
- [x] Quality checks: ruff, pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 6: Enable `S` with tests carve-out and justified src noqa — [step_6.md](./steps/step_6.md)

- [x] Implementation: select `S`, tests per-file ignore, inline `noqa: S608` ×2 and `noqa: S607` with reasons
- [x] Quality checks: ruff, pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 7: Enable `UP`; accept `types.UnionType` in tool CLI unwrapping — [step_7.md](./steps/step_7.md)

- [x] Implementation: schema probe baseline, failing unit test, `_unwrap_annotation` fix, `UP` conversion + stale `noqa: UP007` removal, probe re-run byte-identical, delete `.scratch/`
- [x] Quality checks: ruff, pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 8: CI — rename `ruff-docstrings` job to `ruff` and check `tools/` — [step_8.md](./steps/step_8.md)

- [ ] Implementation: update `.github/workflows/ci.yml` matrix entry
- [ ] Quality checks: ruff, pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

## Pull Request

- [ ] PR review: review full branch diff against `main`, address findings
- [ ] PR summary prepared (note for Marcus: swap required status check `ruff-docstrings` → `ruff` before merge)
