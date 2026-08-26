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

### Step 1: Dependency floor and CI git install of mcp-coder-utils

Details: [step_1.md](./steps/step_1.md)

- [ ] Implementation: `pyproject.toml` floor `mcp-coder-utils>=0.1.6.dev0` + uncomment `[tool.uv.sources]` / `[tool.mcp-coder.install-from-github]` entries; git pre-install at all five `.github/workflows/ci.yml` install sites (extras preserved); upgrade local venv to git `main` and verify `setup_logging` accepts `console_level`; run `python tools/check_no_url_deps.py`; reorder `tools/reinstall_local.sh` / `.bat` only if resolution fails
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

### Step 2: `utils/user_app_data.py` shim and removal of hardcoded home paths

Details: [step_2.md](./steps/step_2.md)

- [ ] Implementation: TDD `tests/utils/__init__.py` + `tests/utils/test_user_app_data.py`; create `src/mcp_tools_sql/utils/user_app_data.py` shim; replace the three `Path.home() / ".mcp-tools-sql"` constructions in `init.py`, `config/loader.py`, `verification/config_files.py`; add `mcp_tools_sql.utils` to `cli.commands` deps in `tach.toml`
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

### Step 3: `OUTPUT` level and per-command `--log-level` defaults

Details: [step_3.md](./steps/step_3.md)

- [ ] Implementation: TDD `tests/cli/conftest.py` autouse `no_op_setup_logging` fixture + parametrized `test_resolve_log_level`; re-export `OUTPUT` from `utils/log_utils.py`; add `_resolve_log_level` to `main.py`, `--log-level` choices + `default=None` + help text, move `command = args.command or "server"` above `setup_logging`, traceback branch uses resolved level
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

### Step 4: Default log file for `server`, console output, and logged startup failures

Details: [step_4.md](./steps/step_4.md)

- [ ] Implementation: TDD four tests in `test_main_dispatch.py` (`test_resolve_log_file`, server-default path, `test_setup_logging_arguments`, migrate friendly-error test to `caplog`); add `_resolve_log_file` to `main.py` with `datetime` / `get_user_app_data_dir` imports; `--log-file` help text; wire `setup_logging(log_level, log_file, console_level=OUTPUT if log_file else None)` (conditional, unguarded); server error branch → `logger.error("%s", exc)` + `logger.log(OUTPUT, hint)`
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

### Step 5: Documentation

Details: [step_5.md](./steps/step_5.md)

- [ ] Implementation: `docs/cli.md` preamble qualifier + three logging table rows + new `### Logging` section; `README.md` `## Logging` subsection; `mcp-tools-sql.md` fix contradictory example + why file-by-default note (leave `--project-dir` lines); `docs/architecture/architecture.md` §6 Logging bullets + §4 `main.py` row
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

## Pull Request

- [ ] PR review: address review comments and fix all findings
- [ ] PR summary: create pull request title and description
