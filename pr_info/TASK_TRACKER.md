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

### Step 1: Consolidate dev toolchain via `mcp-tools-py`

Detail: [step_1.md](./steps/step_1.md)

- [x] Implementation: reshape `[dev]` extra in `pyproject.toml` to the four-entry target shape (add `mcp-tools-py`; remove `black`, `isort`, `pylint`, `mypy`, `ruff`, `tach`, `vulture`, `pytest`, `pytest-asyncio`, `pytest-xdist`, `pydeps`; keep `mcp-workspace`, `mcp-coder`, `pycycle>=0.0.8`). Delete the `pydeps` line from the documented `dev` block in `mcp-tools-sql.md`. Resolve/install `.[dev]` locally and confirm `black --check src tests` is green
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 2: `no-url-deps` script + `test` matrix entry

Detail: [step_2.md](./steps/step_2.md)

- [x] Implementation: create `tools/check_no_url_deps.py` with the verbatim content; add the `no-url-deps` matrix entry to the `test` job in `.github/workflows/ci.yml`; confirm the script exits 0 with the OK message
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 3: File-size guard + `.large-files-allowlist`

Detail: [step_3.md](./steps/step_3.md)

- [x] Implementation: create `.large-files-allowlist` (two-line header + `mcp-tools-sql.md`); add the `file-size` matrix entry to the `test` job in `.github/workflows/ci.yml`; confirm the file-size command exits 0
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 4: `pycycle` cyclic-import check (architecture matrix)

Detail: [step_4.md](./steps/step_4.md)

- [x] Implementation: add the `pycycle` matrix entry to the `architecture` job in `.github/workflows/ci.yml`; run pycycle locally with the exact `--ignore` list and confirm no cycles (matrix line only, no `src/` edits)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 5: Broaden ruff command scope (`src` → `src tests`)

Detail: [step_5.md](./steps/step_5.md)

- [x] Implementation: change the `ruff-docstrings` matrix command in `.github/workflows/ci.yml` from `ruff check src` to `ruff check src tests` (do not touch the `tests/**/*.py` per-file-ignore); confirm `ruff check src tests` exits 0
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

## Pull Request

- [x] Address PR review feedback
- [ ] Final summary of changes
