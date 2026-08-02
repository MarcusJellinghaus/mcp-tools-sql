# Step 16 — `init` multi-connection template + docs

See `pr_info/steps/summary.md` → "Config shape" and "Files created / modified".

## WHERE
- `src/mcp_tools_sql/cli/commands/init.py`
- `docs/architecture/architecture.md`, `docs/cli.md`, `README.md`
- Tests: `tests/cli/test_init.py`

## WHAT
- Update the database-config templates so mssql/postgresql show the new
  `databases` / `default_database` (and optional `description`) shape, keeping a
  commented note that legacy `database = "..."` still works. sqlite template
  unchanged (still just `path`).
- Document the two-axis model, `database="*"` fan-out, `read_databases`, the
  pinned `[queries.*].connection`/`database`, and the security caveat (decision 26:
  `databases` is a routing/discovery list, **not** an authorization boundary).

## HOW
Edit the `_DATABASE_CONFIG_MSSQL` / `_DATABASE_CONFIG_POSTGRESQL` string templates.
For mssql, show `databases = ["sales", "hr"]` + `default_database = "sales"`.
For postgresql, show a single-entry `databases = ["mydb"]` (exactly one allowed).
Add a README config table row and an `architecture.md` §5 note on the conditional
tool surface + `read_databases` naming.

## ALGORITHM
None (template strings + docs).

## DATA
Template strings; documentation prose. No runtime behaviour change.

## TESTS (write first)
- `init --backend mssql` writes a config that `load_database_config` parses into a
  `ConnectionConfig` with `databases == ["sales","hr"]`, `default_database ==
  "sales"` (round-trip through the Step 3 model).
- `init --backend postgresql` round-trips to a single-database connection.
- `init --backend sqlite` unchanged.
- Existing init snapshot/behaviour tests updated.

## LLM PROMPT
> Implement Step 16 from `pr_info/steps/step_16.md` (context in
> `pr_info/steps/summary.md`). Update the mssql/postgresql database-config
> templates in `cli/commands/init.py` to the `databases`/`default_database` shape
> (legacy `database` noted as still supported; sqlite unchanged), and document the
> two-axis model, `database="*"` fan-out, `read_databases`, pinned query
> connection/database, and the decision-26 security caveat in `README.md`,
> `docs/architecture/architecture.md` §5, and `docs/cli.md`. Write/adjust
> `tests/cli/test_init.py` first (templates round-trip through the config model).
> Run pylint, pytest (`-n auto` + unit markers), mypy, lint-imports/tach; all
> green. One commit.
