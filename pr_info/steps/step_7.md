# Step 7 — Documentation: `${VAR}` syntax + TLS knobs

## Goal

Update user-facing docs to match the new credential mechanism (`${VAR}`)
and the new TLS fields (`encrypt`, `trust_server_certificate`). No code
changes; no tests.

## WHERE

| Action | Path |
|---|---|
| Modify | `mcp-tools-sql.md` |
| Modify | `docs/cli.md` |

## WHAT

### `mcp-tools-sql.md`

- Replace every `credential_env_var = "X"` example with
  `password = "${X}"`.
- Add a short subsection under the connection-config docs:
  *"Environment variable substitution"*. Cover:
  - `${VAR}` works in any string field of `[connections.*]`.
  - Substitution happens **only** in the database config
    (`~/.mcp-tools-sql/config.toml`), never in query SQL.
  - Unset variables fail at load time with an explicit `ValueError`.
- Add a short subsection: *"TLS / Encryption"*. Cover:
  - Defaults: `encrypt = true`, `trust_server_certificate = false`
    (Driver 18 secure defaults).
  - Local SQL Server and the CI container do **not** have a valid cert →
    you must set `trust_server_certificate = true` there.

### `docs/cli.md`

- Update any MSSQL connection-config snippet to use
  `password = "${MSSQL_PASSWORD}"` instead of `credential_env_var =
  "MSSQL_PASSWORD"`.
- Update PostgreSQL snippets to the same `${POSTGRES_PASSWORD}` pattern
  (consistency).
- If `docs/cli.md` documents the `verify` output, note the new
  `kerberos_ticket` row (mssql + trusted_connection + Linux only).

## HOW

- Use `mcp__workspace__read_file` to inspect the current text of each doc
  and `mcp__workspace__edit_file` for surgical replacements (one block at
  a time).
- Keep prose minimal: 2-3 sentences per new subsection.

## DATA

None — pure documentation.

## Tests

None.

## Checks

- `mcp__tools-py__run_pylint_check` (no code changes, but run to confirm
  nothing regressed)
- `mcp__tools-py__run_mypy_check`
- `mcp__tools-py__run_pytest_check(extra_args=["-n", "auto", "-m", "not git_integration and not claude_cli_integration and not claude_api_integration and not formatter_integration and not github_integration and not langchain_integration"])`
- `./tools/format_all.sh`
- Single commit.

## LLM Prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_7.md`. Update
> `mcp-tools-sql.md` and `docs/cli.md` to replace `credential_env_var`
> examples with `password = "${VAR}"` syntax, document the
> `encrypt` / `trust_server_certificate` defaults and when to override
> them, and mention the `kerberos_ticket` verify row (Linux + mssql +
> trusted_connection). No code changes. Run pylint, mypy, pytest via MCP
> tools per CLAUDE.md to confirm nothing regressed. End with a single
> commit.
