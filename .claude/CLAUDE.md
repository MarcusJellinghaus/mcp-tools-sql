## About this repo

`mcp-tools-sql` is an MCP server for safe, configurable SQL database access. It exposes schema introspection, parameterized queries, and structured updates as MCP tools for Claude and other LLM-based applications. Primary target is MS SQL Server with PostgreSQL and SQLite as secondary backends.

## MCP Tools — mandatory

Use MCP tools for **all** operations. Never use `Read`, `Write`, `Edit`, or `Bash` for tasks that have an MCP equivalent. If no MCP equivalent exists, use Bash. Check the tool mapping table below first.

### Tool mapping

| Task | MCP tool |
|------|----------|
| Read file | `mcp__mcp-workspace__read_file` |
| Edit file | `mcp__mcp-workspace__edit_file` |
| Write file | `mcp__mcp-workspace__save_file` |
| Append to file | `mcp__mcp-workspace__append_file` |
| Delete file | `mcp__mcp-workspace__delete_this_file` |
| Move file | `mcp__mcp-workspace__move_file` |
| List directory | `mcp__mcp-workspace__list_directory` |
| Search files | `mcp__mcp-workspace__search_files` |
| Read reference project | `mcp__mcp-workspace__read_reference_file` |
| List reference dir | `mcp__mcp-workspace__list_reference_directory` |
| Get reference projects | `mcp__mcp-workspace__get_reference_projects` |
| Search reference files | `mcp__mcp-workspace__search_reference_files` |
| Get base branch | `mcp__mcp-workspace__get_base_branch` |
| Check file size | `mcp__mcp-workspace__check_file_size` (default max_lines=750) |
| Check branch status | `mcp__mcp-workspace__check_branch_status` |
| Run pytest | `mcp__mcp-tools-py__run_pytest_check` |
| Run pylint | `mcp__mcp-tools-py__run_pylint_check` |
| Run mypy | `mcp__mcp-tools-py__run_mypy_check` |
| Run vulture | `mcp__mcp-tools-py__run_vulture_check` |
| Run lint-imports | `mcp__mcp-tools-py__run_lint_imports_check` |
| Run ruff check | `mcp__mcp-tools-py__run_ruff_check` |
| Run ruff fix | `mcp__mcp-tools-py__run_ruff_fix` |
| Run bandit | `mcp__mcp-tools-py__run_bandit_check` |
| Format code (black+isort) | `mcp__mcp-tools-py__run_format_code` |
| Get library source | `mcp__mcp-tools-py__get_library_source` |
| Refactoring | `mcp__mcp-tools-py__move_symbol`, `move_module`, `rename_symbol`, `list_symbols`, `find_references` |
| Git read-only (fetch, ls-tree, show, ls-files, ls-remote, rev-parse, branch list) | `mcp__mcp-workspace__git` |
| `gh issue view` | `mcp__mcp-workspace__github_issue_view` |
| `gh issue list` | `mcp__mcp-workspace__github_issue_list` |
| `gh pr view` | `mcp__mcp-workspace__github_pr_view` |
| `gh search` | `mcp__mcp-workspace__github_search` |

Sibling repos are readable in full via the reference tools and `git` with `reference_name` (`get_reference_projects` lists them). Check there before asking about another repo.

## Code quality checks

After making code changes, run:

```
mcp__mcp-tools-py__run_pylint_check
mcp__mcp-tools-py__run_pytest_check
mcp__mcp-tools-py__run_mypy_check
```

All checks must pass before proceeding.

**Ruff:** use `mcp__mcp-tools-py__run_ruff_check`. Do not call `ruff` directly.

**Pytest:** always use `extra_args: ["-n", "auto"]` for parallel execution.

When debugging test failures, add `"-v", "-s", "--tb=short"` to extra_args.

## Git operations

**Allowed commands via Bash tool.** These have no MCP equivalent — use Bash directly. Skills that instruct bash commands (e.g. `git commit`) must also use Bash.

```
git commit / add / rebase / push
gh issue view (cross-repo only — otherwise use the MCP tool)
mcp-coder gh-tool set-status <label>
```

**Status labels:** use `mcp-coder gh-tool set-status` to change issue workflow status — never use raw `gh issue edit` with label flags.

**Slash-prefixed `gh` arguments:** prefix with `MSYS_NO_PATHCONV=1` — Git Bash rewrites a leading `/` into a Windows path.

**Compact diff:** use `mcp__mcp-workspace__git` for code review. Has compact diff built-in with exclude pattern support.

**Before every commit:** run `mcp__mcp-tools-py__run_format_code`, then stage and commit.

**Bash discipline:** no `cd` prefix, no `git -C` — commands already run in the project directory. Don't chain approved with unapproved commands. Run them separately.

**Commit messages:** standard format. See Writing style for length. No attribution footers.

## Shared Libraries

`log_utils` in `src/mcp_tools_sql/utils/` is a thin shim over `mcp-coder-utils`. Always import through the local shim (`from mcp_tools_sql.utils.log_utils import ...`), not from `mcp_coder_utils` directly. Enforced by import-linter (`forbidden-imports` contract in `.importlinter`).

## Writing style

Be concise. Shorter is better — chat, commits, PRs, docs, comments alike.

Say it once. Never restate what the reader can already see: the diff, the code, the issue, or my own earlier message. Cut it; don't rephrase it.

If a sentence isn't load-bearing, delete it.

## Asking questions

Never use the AskUserQuestion tool. Ask questions as plain text in the chat.

## Obsidian knowledge base

Shared knowledge base across my repos (`obsidian-dev-wiki`), via the `obsidian-wiki` MCP server.

**Read at the start of non-trivial work:** `Home.md` (index), the `Repos/<current repo>.md` note, and any `Processes/` note matching the task. If a process note covers the task, follow it rather than improvising.

**Write only what passes all three tests:**

- *durable* — still true in 6 months (not status, versions, or task state)
- *general* — applies beyond the one issue that produced it
- *homeless* — no better place already exists

Existing homes, check before writing: code and docstrings; the repo's `docs/`; CLAUDE.md for how-I-work rules; the GitHub issue for a single defect's root cause; git history for what changed when.

**Always write to `Field Notes/`**, for Marcus to promote. Only edit `Repos/`, `Processes/`, or `Plans/` when Marcus explicitly asks for it. If an existing note already covers the topic, name it in the Field Note (`Promote into [[Note Name]]`) instead of editing that note. Follow `Conventions.md` for frontmatter and naming.

## Testing MCP servers

To verify an MCP server is running and its tools are discoverable, use `mcp-coder prompt`:

```bash
mcp-coder prompt --output-format json "List all MCP tools you have access to."
```

This spawns a separate Claude session that connects to all configured MCP servers and reports available tools.

## MCP server issues

Alert immediately if MCP tools are not accessible — this blocks all work.
