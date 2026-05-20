# Step 10 — Update architecture documentation

**Goal:** Add `verification` to `docs/architecture/architecture.md`: layer
diagram, module table, and a short extraction note.

## WHERE

### Modified files
- `docs/architecture/architecture.md`

## WHAT

### 1. Layer diagram (Section 4 — "Building Block View → Layer Architecture")

Insert `verification` as a tool-tier orchestrator sitting just below the
Tool Layer:

```
├─────────────────────────────────────────────────────┤
│  Tool Layer                                         │
│  ├── mcp_tools_sql.schema_tools                     │
│  ├── mcp_tools_sql.query_tools                      │
│  ├── mcp_tools_sql.update_tools                     │
│  └── mcp_tools_sql.validation_tools                 │
├─────────────────────────────────────────────────────┤
│  Verification Layer                                 │
│  └── mcp_tools_sql.verification (subpackage)        │
├─────────────────────────────────────────────────────┤
│  Infrastructure Layer                               │
│  ...                                                │
```

### 2. Module table (Section 4 — "Key Modules")

Append one row:

| Module | Responsibility |
|--------|---------------|
| `verification/` | Verifier engine: environment, config, dependencies, builtin, connection, queries, updates. Orchestrated by `verify_all`. Consumed by the `verify` CLI subcommand. |

### 3. Extraction note

Add a short paragraph (after the existing "CLI Layer" subsection):

```markdown
### Verification Layer (`mcp_tools_sql.verification`)

The verification engine was extracted from `cli/commands/verify.py` in
issue #21 to keep the CLI module under the 600-line file-size limit and
to make the engine reusable from non-CLI consumers (planned: MCP-server
health endpoint, programmatic validation in tests). The orchestrator
`verify_all(config_path, db_config_path)` composes every section in a
canonical order and returns `(sections, skip_summary)`; the CLI shim
is a pure printer that iterates `sections` as-is. The subpackage sits
at the `tool_implementation` layer (same as `schema_tools`/`query_tools`)
in `tach.toml`, and on its own line in `.importlinter` (above
`schema_tools|...`) because it imports from `schema_tools.load_default_queries`
and `query_helpers.extract_sql_params`.
```

## HOW

Use `mcp__mcp-workspace__edit_file` with exact-string anchors. Three
separate edits (one per insertion point above).

## ALGORITHM

No algorithm — pure documentation.

## DATA

N/A.

## Checks

Run after edits:
- `mcp__mcp-tools-py__run_pylint_check` — sanity, should be unaffected
- `mcp__mcp-tools-py__run_mypy_check` — sanity, should be unaffected
- `mcp__mcp-tools-py__run_pytest_check(extra_args=["-n", "auto", "-m", "not git_integration and not claude_cli_integration and not claude_api_integration and not formatter_integration and not github_integration and not langchain_integration"])`
- `mcp__mcp-tools-py__run_tach_check`
- `mcp__mcp-tools-py__run_lint_imports_check`

All must pass.

Manually verify by reading the diff: the diagram block is well-formed
ASCII art and the module table is valid Markdown.

## LLM Prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_10.md`.
> Implement step 10: update `docs/architecture/architecture.md` with
> three targeted insertions:
>
> 1. In the layer diagram (Section 4 → "Layer Architecture"), add a
>    "Verification Layer" block between the Tool Layer and the
>    Infrastructure Layer.
> 2. In the "Key Modules" table (Section 4), append one row for
>    `verification/`.
> 3. After the existing "CLI Layer" prose subsection, add a new
>    "Verification Layer (`mcp_tools_sql.verification`)" subsection
>    using the markdown shown in step_10.md.
>
> Use `edit_file` with exact-string anchors. Do not reformat unrelated
> sections. Run all checks; all must pass before committing.
