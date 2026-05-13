# Step 6 — Kerberos `klist -s` check in `verify`

## Goal

When `trusted_connection=true` is configured for `mssql` on **Linux**, run
`klist -s` to check for a cached Kerberos ticket. Non-zero return code → an
`[ERR]` row. Implements Decisions #10 and #19.

## WHERE

| Action | Path |
|---|---|
| Modify | `src/mcp_tools_sql/cli/commands/verify.py` (add `import subprocess`, add `_check_kerberos_ticket`, wire into `verify_connection`) |
| Modify | `tests/cli/test_verify.py` |

Imports to add to `cli/commands/verify.py`:

- `import subprocess` (for `subprocess.run` + `subprocess.TimeoutExpired`)
- `import sys` (already present in most likelihood — add if missing, for
  the `sys.platform == "linux"` guard)

## WHAT

```python
# verify.py — new private helper
def _check_kerberos_ticket() -> tuple[bool, str, str]: ...
```

Returned tuple: `(ok, value, error)`. Used inside `verify_connection` to
add a `kerberos_ticket` row to the result dict — but only when:

- `connection.backend == "mssql"`
- `connection.trusted_connection is True`
- `sys.platform == "linux"`

On any other platform, the check is skipped entirely (no row added) — the
behaviour on Windows (SSPI) is implicit; this check is Linux-specific.

## HOW

- Use `subprocess.run(["klist", "-s"], check=False, capture_output=True,
  timeout=5)`. `klist -s` is the "silent" mode: exit 0 = ticket cached,
  non-zero = no ticket.
- `FileNotFoundError` (no `klist` installed) → `[ERR]` with
  `install_hint = "Install krb5-user (apt) or krb5-workstation (dnf)"`.
- `subprocess.TimeoutExpired` → `[ERR]` with `error=str(exc)`.

## ALGORITHM

```
def _check_kerberos_ticket():
    try:
        proc = subprocess.run(
            ["klist", "-s"], check=False,
            capture_output=True, timeout=5)
    except FileNotFoundError:
        return False, "klist not installed", "Install Kerberos client tools (krb5-user / krb5-workstation)"
    except subprocess.TimeoutExpired as exc:
        return False, "klist timeout", str(exc)
    if proc.returncode == 0:
        return True, "cached ticket present", ""
    return False, "no cached ticket", "Run `kinit` to obtain a Kerberos ticket"
```

In `verify_connection`, after the existing credentials row:

```python
if (connection.backend == "mssql"
        and connection.trusted_connection
        and sys.platform == "linux"):
    ok, value, error = _check_kerberos_ticket()
    result["kerberos_ticket"] = _entry(ok=ok, value=value, error=error)
```

`overall_ok` already aggregates entries, so the existing logic flips to
`False` when this row is `[ERR]`.

## DATA

- One new result-dict key: `"kerberos_ticket"` (only present on Linux +
  mssql + trusted_connection).

## Tests (write FIRST)

```python
# tests/cli/test_verify.py — additions

@pytest.fixture
def linux_platform(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")


def _trusted_mssql() -> ConnectionConfig:
    return ConnectionConfig(backend="mssql", host="h", port=1433,
                             database="d", trusted_connection=True)


@pytest.fixture
def _stub_create_backend(monkeypatch):
    """Replace `verify.create_backend` so tests never touch real pyodbc.

    Returns a `MagicMock` whose returned backend stubs the methods that
    `verify_connection` calls: `connect`, `execute_query`, `close`. Each
    Kerberos test reuses this fixture instead of re-stubbing inline.
    """
    backend = MagicMock(name="stub_backend")
    backend.connect.return_value = None
    backend.execute_query.return_value = [{"v": 1}]
    backend.close.return_value = None
    factory = MagicMock(return_value=backend)
    monkeypatch.setattr(
        "mcp_tools_sql.cli.commands.verify.create_backend", factory
    )
    return factory


class TestKerberosCheck:
    def test_klist_zero_returns_ok(
        monkeypatch, linux_platform, _stub_create_backend
    ):
        proc = MagicMock(returncode=0)
        monkeypatch.setattr("subprocess.run", MagicMock(return_value=proc))
        result, _ = verify_cmd.verify_connection(_trusted_mssql())
        assert result["kerberos_ticket"]["ok"] is True

    def test_klist_nonzero_returns_err(
        monkeypatch, linux_platform, _stub_create_backend
    ):
        proc = MagicMock(returncode=1)
        monkeypatch.setattr("subprocess.run", MagicMock(return_value=proc))
        result, _ = verify_cmd.verify_connection(_trusted_mssql())
        assert result["kerberos_ticket"]["ok"] is False
        assert "kinit" in result["kerberos_ticket"]["error"].lower() or \
               "ticket" in result["kerberos_ticket"]["error"].lower()

    def test_klist_missing_returns_err(
        monkeypatch, linux_platform, _stub_create_backend
    ):
        monkeypatch.setattr("subprocess.run",
                            MagicMock(side_effect=FileNotFoundError()))
        result, _ = verify_cmd.verify_connection(_trusted_mssql())
        assert result["kerberos_ticket"]["ok"] is False

    def test_non_linux_platforms_skip_check(monkeypatch, _stub_create_backend):
        monkeypatch.setattr(sys, "platform", "win32")
        result, _ = verify_cmd.verify_connection(_trusted_mssql())
        assert "kerberos_ticket" not in result

    def test_non_trusted_skips_check(linux_platform, _stub_create_backend):
        # password auth on Linux — no kerberos row expected
        conn = ConnectionConfig(backend="mssql", host="h", port=1433,
                                database="d", password="p")
        result, _ = verify_cmd.verify_connection(conn)
        assert "kerberos_ticket" not in result
```

**Note**: the `_stub_create_backend` fixture replaces
`mcp_tools_sql.cli.commands.verify.create_backend` so the tests never
touch real pyodbc. Centralising this in one fixture (instead of
duplicating the monkeypatch in each of the four Kerberos tests) keeps the
test module readable and ensures all four tests share an identical stub
contract.

## Checks

- `mcp__tools-py__run_pylint_check`
- `mcp__tools-py__run_mypy_check`
- `mcp__tools-py__run_pytest_check(extra_args=["-n", "auto", "-m", "not git_integration and not claude_cli_integration and not claude_api_integration and not formatter_integration and not github_integration and not langchain_integration"])`
- `./tools/format_all.sh`
- Single commit.

## LLM Prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_6.md`. Add the
> `_check_kerberos_ticket()` helper and wire it into `verify_connection`
> (mssql + trusted_connection + Linux only). Write the tests in
> `tests/cli/test_verify.py` first (TDD) with `subprocess.run` mocked and
> `sys.platform` patched. Run pylint, mypy, pytest via MCP tools per
> CLAUDE.md after every edit. End with a single commit.
