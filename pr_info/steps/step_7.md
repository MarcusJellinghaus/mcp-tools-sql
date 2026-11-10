# Step 7 — Public `toolset.verify` and the `utils/toolkit.py` shim

## LLM prompt
Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_7.md`.
Precondition: `from mcp_coder_utils.toolkit import VerifyItem` must work in the
project environment — check it with a scratch probe
(`.scratch/test_probe.py`, run via `run_pytest_check` with
`extra_args: ["-p", "no:cacheprovider", ".scratch/test_probe.py"]`, then delete
`.scratch/`). If it fails, write one line to `pr_info/.blocked.txt` and stop.
Write the tests first, then the code. Run `run_format_code`, pylint, pytest
(`extra_args: ["-n", "auto"]`), mypy, ruff, lint-imports, tach, vulture and
deptry; all must pass. One commit:
`feat(toolset): public verify via the shared VerifyItem contract`.

## WHERE
- New: `src/mcp_tools_sql/utils/toolkit.py`
- `src/mcp_tools_sql/toolset.py`
- Tests: `tests/test_toolset_verify.py` (new), `tests/test_module_imports.py`

## WHAT
`utils/toolkit.py`:
```python
"""Verification result contract — thin shim over mcp-coder-utils."""

from mcp_coder_utils.toolkit import VerifyItem, VerifyStatus

__all__ = ["VerifyItem", "VerifyStatus"]
```

`toolset.py`:
```python
if TYPE_CHECKING:
    from mcp_tools_sql.utils.toolkit import VerifyItem, VerifyStatus
    from mcp_tools_sql.verification import CheckResult

def verify(
    query_config: Path,
    database_config: Path | None = None,
    *,
    connect: bool = False,
) -> list[VerifyItem]:
def _status(row: CheckResult) -> VerifyStatus
def _message(row: CheckResult) -> str
```
Import `collect_sections` from `mcp_tools_sql.verification.orchestrator` at
module top. Import `VerifyItem` **inside** `verify`
(`# pylint: disable=import-outside-toplevel`), with a comment: toolkit imports
jsonschema; `build_toolset` and server start must not pay for it (#39).
Leave the inner `verify` closure in `_build_verify_tool` as is.

## ALGORITHM
```
from mcp_tools_sql.utils.toolkit import VerifyItem       # lazy
sections = collect_sections(query_config, database_config, connect=connect,
                            build_probe=lambda: build_toolset(query_config, database_config).close())
return [VerifyItem(name=f"{s['title'].lower()}.{key}", status=_status(row),
                   message=_message(row), hint=row.get("install_hint") or None)
        for s in sections for key, row in s["checks"].items()]
_status:  "ok" if row["ok"] else "warning" if row["severity"] == "warning" else "error"
_message: " - ".join(p for p in (row.get("value", ""), row.get("error", "")) if p)
```
Docstring: never raises for problems it detects; `connect=False` opens no
connection, does no DNS lookup and runs no subprocess.

## Tests (write first) — `tests/test_toolset_verify.py`
Sqlite configs in `tmp_path`; patch `mcp_tools_sql.backends.connection_check.pyodbc_version` /
`odbc_drivers` where mssql is involved.
- **No connection under `connect=False`:** config with default sqlite + `prod`
  mssql (host, database, `trusted_connection = true`), `sys.platform` patched
  to `"linux"`. Patch to raise `AssertionError`: `SQLiteBackend.connect` and
  every SQLite fresh-connection path (find the `sqlite3.connect` call sites in
  `backends/sqlite.py`), `MSSQLBackend._open_connection`,
  `socket.gethostbyname`, `mcp_tools_sql.verification.connection.execute_subprocess`.
  `verify(...)` returns `toolset.build` with status `ok`, and no item whose
  name ends in `.select_1`, `.dns_lookup`, `.kerberos_ticket`, `.sql`, nor
  any `updates.*` item.
- default sqlite + mssql `prod` without pyodbc → `dependencies.prod.pyodbc`
  `error` with hint containing `[mssql]`; `toolset.build` is `warning`
  "skipped (earlier errors)".
- `pg` postgresql connection → `dependencies.pg.backend` `error` "unsupported backend".
- configured ODBC driver missing → `dependencies.prod.odbc_driver` `error`
  whose message names the driver and the installed ones.
- invalid query name (`[queries."bad-name"]`) → `toolset.build` `error` mentioning "Invalid query name".
- non-read-only query (`sql = "DELETE FROM customers"`) under `connect=False`
  → `queries.<name>.read_only[sqlite]` `error`.
- `connect=True` with the default connection down → config-only
  `queries.*` rows present, `queries.<name>.sql` and `updates.*` are `warning`
  "skipped (connection default unreachable)"; `connect=True` never returns
  fewer names than `connect=False` on the same config.
- Mapping: a sqlite connection named `Prod` → names keep `Prod`
  (`dependencies.Prod.info`, `connection.Prod/main.backend`); section lowercased;
  message `"value - error"` when both set; `hint is None` when no install hint;
  no name starts with `install instructions`.
- Explicit nonexistent `database_config` → `config.database_config_path`
  `error`, `toolset.build` `warning` skipped; `verify` does not raise.

`tests/test_module_imports.py` `_TOOLSET_NO_MCP_SCRIPT`: after the
`build_toolset` block, print `"mcp_coder_utils.toolkit" in sys.modules`; then
call `verify(qcfg, dbcfg)` (default `connect=False`) and print the existing
`mcp` check. Assert stdout lines are `["False", "False"]`.

## DATA
`list[VerifyItem]` — `name: str`, `status: "ok" | "warning" | "error"`,
`message: str`, `hint: str | None`; order = section order of `collect_sections`.
