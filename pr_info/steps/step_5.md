# Step 5 — Config-only section parameters (CONNECTION `connect`, QUERIES `registry=None`)

## LLM prompt
Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_5.md`.
Write the tests first, then the code. Run `run_format_code`, pylint, pytest
(`extra_args: ["-n", "auto"]`), mypy and ruff; all must pass. `verify_all`
output must not change (`verify_snapshot.txt` unchanged). One commit:
`feat(verification): config-only mode for CONNECTION and QUERIES`.

## WHERE
- `src/mcp_tools_sql/verification/connection.py`
- `src/mcp_tools_sql/verification/queries.py`
- `src/mcp_tools_sql/verification/orchestrator.py` (`_verify_connections` only)
- Tests: `tests/verification/test_connection.py`, `tests/verification/test_queries.py`,
  `tests/verification/test_orchestrator.py`

## WHAT
```python
def verify_connection(target, backend, *, probe_error: str = "", connect: bool = True) -> dict[str, CheckResult]
```
`connect=False`: skip `dns_lookup`, `kerberos_ticket` and `select_1`; every
config row (backend, driver, host_port / path incl. `:memory:` warning,
database, credentials, conn_string) is emitted as today. Wrap the three probe
blocks in `if connect:`.

```python
def _verify_connections(targets: ResolvedTargets, registry: BackendRegistry | None) -> tuple[...]
```
`registry is None`: no `registry.backend_for`; call
`verify_connection(target, None, connect=False)`. Return shape unchanged.

```python
def verify_queries(queries, targets, registry: BackendRegistry | None, reachable) -> dict[str, CheckResult]
def verify_one_query(name, qcfg, targets, registry: BackendRegistry | None, reachable)
def _verify_query_checks(name, qcfg, targets, registry: BackendRegistry | None, reachable)
```
## ALGORITHM (`_verify_query_checks`)
```
pin error:  if registry is not None: result[".sql"] = ERR; then read_only/params/max_rows rows as today
resolved:   read_only_rows = ...
            if registry is not None:            # registry None = config-only, no .sql row
                .sql = skipped-not-read-only | EXPLAIN (reachable) | skipped (unreachable)   # unchanged logic
            rest unchanged (read_only rows, params, max_rows_default, max_rows_hard)
```
Row order for `registry is not None` is unchanged (snapshot). Update docstrings.

## Tests (write first)
- `test_connection.py`: mssql config with host + `trusted_connection`,
  `sys.platform` patched to `"linux"`, `connect=False`, `backend=None`, and
  `socket.gethostbyname` / `execute_subprocess` patched to raise
  `AssertionError` → no `dns_lookup`, `kerberos_ticket`, `select_1` rows;
  `driver`, `host_port`, `credentials`, `conn_string` present. mssql with empty
  host → `host_port` ERR. sqlite `:memory:` → `path` warning, no `select_1`.
- `test_queries.py`: `registry=None`, `reachable={}` → no `<name>.sql` key;
  `read_only[...]`, `params`, `max_rows_*`, `description` rows present; a
  non-read-only query (`DELETE FROM t`) → `read_only[sqlite]` ERR; a bad pin →
  `read_only` / `params` ERR rows and no `.sql` row.
- `test_orchestrator.py`: `_verify_connections(targets, None)` never calls
  `create_backend` (patch it to raise) and has no `select_1` rows.

## DATA
Return types unchanged; only the presence of probe / `.sql` rows depends on the new arguments.
