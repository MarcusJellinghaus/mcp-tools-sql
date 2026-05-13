# Step 3 — MSSQL connection-string builder

## Goal

Pure function that maps `ConnectionConfig` → ODBC connection-string. No live
DB required. Fully unit-tested. Becomes the input to `pyodbc.connect()` in
Step 4.

## WHERE

| Action | Path |
|---|---|
| Modify | `src/mcp_tools_sql/backends/mssql.py` (add module-level function) |
| Create | `tests/backends/test_mssql.py` (with the `TestConnectionStringBuilder` class) |

## WHAT

```python
# src/mcp_tools_sql/backends/mssql.py
def _build_connection_string(config: ConnectionConfig) -> str: ...
```

The function is **module-private** but importable for tests:
`from mcp_tools_sql.backends.mssql import _build_connection_string`.

## HOW

ODBC connection-string rules to implement:

- `Driver={<driver>}` — always wrap driver name in `{...}`.
- `Server=<host>,<port>` — comma syntax, **not** `host:port`. If
  `config.port == 0`, emit `Server=<host>,1433`.
- `Database=<value>` — escape if needed.
- `Trusted_Connection=yes` when `trusted_connection=True`; **omit**
  `UID`/`PWD`. Otherwise emit `UID=<username>;PWD={<password>}`.
- `Encrypt=yes|no` from `config.encrypt`.
- `TrustServerCertificate=yes|no` from `config.trust_server_certificate`.

### Escaping rule

If a value contains any of `;`, `=`, `{`, `}`, or starts/ends with
whitespace, wrap the whole value in `{ ... }` and double every embedded `}`
(per ODBC spec). Otherwise emit the value bare.

```python
def _odbc_escape(value: str) -> str: ...
```

## ALGORITHM

```
NEEDS_BRACES = set(";={}")

def _odbc_escape(v):
    if not v: return v
    if any(c in NEEDS_BRACES for c in v) or v != v.strip():
        return "{" + v.replace("}", "}}") + "}"
    return v

def _build_connection_string(c):
    port = c.port or 1433
    parts = [f"Driver={{{c.driver}}}",
             f"Server={c.host},{port}",
             f"Database={_odbc_escape(c.database)}"]
    if c.trusted_connection:
        parts.append("Trusted_Connection=yes")
    else:
        parts.append(f"UID={_odbc_escape(c.username)}")
        parts.append(f"PWD={_odbc_escape(c.password)}")
    parts.append(f"Encrypt={'yes' if c.encrypt else 'no'}")
    parts.append(f"TrustServerCertificate={'yes' if c.trust_server_certificate else 'no'}")
    return ";".join(parts)
```

## DATA

Returned string: semicolon-joined `key=value` pairs (no trailing `;`).
Order is deterministic so tests can assert on exact strings.

## Tests (write FIRST)

`tests/backends/test_mssql.py`:

```python
from mcp_tools_sql.backends.mssql import _build_connection_string, _odbc_escape
from mcp_tools_sql.config.models import ConnectionConfig


class TestOdbcEscape:
    def test_plain_value_unchanged(): _odbc_escape("plain") == "plain"
    def test_value_with_semicolon_wrapped(): _odbc_escape("a;b") == "{a;b}"
    def test_value_with_equals_wrapped(): _odbc_escape("a=b") == "{a=b}"
    def test_value_with_closing_brace_doubled(): _odbc_escape("a}b") == "{a}}b}"
    def test_value_with_leading_space_wrapped(): _odbc_escape(" a") == "{ a}"
    def test_empty_value_returned_empty(): _odbc_escape("") == ""


class TestConnectionStringBuilder:
    def test_password_auth_basic():
        c = ConnectionConfig(backend="mssql", host="h", port=1433,
                             database="d", username="u", password="p")
        s = _build_connection_string(c)
        assert "Server=h,1433" in s
        assert "UID=u" in s and "PWD=p" in s
        assert "Trusted_Connection" not in s
        assert "Encrypt=yes" in s
        assert "TrustServerCertificate=no" in s

    def test_trusted_connection_omits_uid_pwd():
        c = ConnectionConfig(backend="mssql", host="h", port=1433,
                             database="d", trusted_connection=True)
        s = _build_connection_string(c)
        assert "Trusted_Connection=yes" in s
        assert "UID=" not in s and "PWD=" not in s

    def test_port_zero_defaults_to_1433():
        c = ConnectionConfig(backend="mssql", host="h", port=0,
                             database="d", trusted_connection=True)
        assert "Server=h,1433" in _build_connection_string(c)

    def test_port_uses_comma_not_colon():
        c = ConnectionConfig(backend="mssql", host="h", port=1234,
                             database="d", trusted_connection=True)
        s = _build_connection_string(c)
        assert "Server=h,1234" in s
        assert "h:1234" not in s

    def test_password_with_semicolon_escaped():
        c = ConnectionConfig(backend="mssql", host="h", port=1433,
                             database="d", username="u", password="a;b")
        assert "PWD={a;b}" in _build_connection_string(c)

    def test_password_with_brace_doubled():
        c = ConnectionConfig(backend="mssql", host="h", port=1433,
                             database="d", username="u", password="a}b")
        assert "PWD={a}}b}" in _build_connection_string(c)

    def test_encrypt_false():
        c = ConnectionConfig(backend="mssql", host="h", port=1433,
                             database="d", trusted_connection=True,
                             encrypt=False)
        assert "Encrypt=no" in _build_connection_string(c)

    def test_trust_server_certificate_true():
        c = ConnectionConfig(backend="mssql", host="h", port=1433,
                             database="d", trusted_connection=True,
                             trust_server_certificate=True)
        assert "TrustServerCertificate=yes" in _build_connection_string(c)

    def test_driver_wrapped_in_braces():
        c = ConnectionConfig(backend="mssql", host="h", port=1433,
                             database="d", trusted_connection=True,
                             driver="ODBC Driver 18 for SQL Server")
        assert "Driver={ODBC Driver 18 for SQL Server}" in \
               _build_connection_string(c)
```

## Checks

- `mcp__tools-py__run_pylint_check`
- `mcp__tools-py__run_mypy_check`
- `mcp__tools-py__run_pytest_check(extra_args=["-n", "auto", "-m", "not git_integration and not claude_cli_integration and not claude_api_integration and not formatter_integration and not github_integration and not langchain_integration"])`
- `./tools/format_all.sh`
- Single commit.

## LLM Prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_3.md`. Implement
> Step 3 exactly: add `_odbc_escape` and `_build_connection_string` as
> module-level functions in `src/mcp_tools_sql/backends/mssql.py` and write
> `tests/backends/test_mssql.py` with the `TestOdbcEscape` and
> `TestConnectionStringBuilder` classes. Tests first (TDD). Run pylint,
> mypy, pytest via MCP tools per CLAUDE.md after every edit. End with a
> single commit. Do **not** implement the `MSSQLBackend` methods yet —
> that is Step 4.
