# Step 2 – Timeout primitives + SQLite statement timeout

## LLM prompt
Read `pr_info/steps/summary.md` (sections 1 and 2) and this file. Implement
step 2 only, test-first: add `QueryTimeoutError`, `Deadline` and
`translate_timeout` to `backends/base.py`, and enforce the SQLite statement
timeout on every statement path through a per-statement context manager. Run
pylint, pytest (`-n auto`), mypy; format; one commit.

## Precondition
Before writing the implementation, confirm with a scratch probe
(`.scratch/test_probe.py`, see CLAUDE.md) that a progress handler returning
non-zero makes `cursor.fetchall()` raise `sqlite3.OperationalError` whose
`sqlite_errorcode == 9`. If it does not, write one line to
`pr_info/.blocked.txt` and stop. Delete `.scratch/` afterwards.

## WHERE
- `src/mcp_tools_sql/backends/base.py`
- `src/mcp_tools_sql/backends/sqlite.py`
- Tests: `tests/backends/test_base_timeout.py` (new),
  `tests/backends/test_sqlite_timeout.py` (new)

## WHAT
```python
# backends/base.py
_SQLITE_INTERRUPT = 9
_SQLSTATE_TIMEOUT = "HYT00"

class QueryTimeoutError(Exception):
    """A statement exceeded the connection's query_timeout_seconds."""
    def __init__(self, seconds: int) -> None:
        self.seconds = seconds
        super().__init__(f"Query aborted after {seconds} s (statement timeout).")

@dataclass
class Deadline:
    """Caller-set counting deadline (time.monotonic()), None = not armed."""
    at: float | None = None

def translate_timeout(exc: BaseException, seconds: int) -> QueryTimeoutError | None: ...

# backends/sqlite.py
_PROGRESS_STEPS = 1000  # VM instructions between deadline checks

@contextmanager
def _statement_deadline(
    conn: sqlite3.Connection, seconds: int, counting: Deadline | None = None
) -> Iterator[None]: ...
```

## HOW
- Wrap with `with _statement_deadline(conn, self._config.query_timeout_seconds):`
  the execute **and** fetch of: `execute_query`, `execute_readonly_query`,
  `execute_readonly_query_with_columns`, `execute_update` (including
  `commit`), `explain`. On the read-only connections arm it after
  `PRAGMA query_only = ON`.
- `get_isolated_connection` is unchanged (it is only used on the SQL Server
  path of `_explain`; SQLite `_explain` calls `backend.explain`).
- `translate_timeout` must not import `sqlite3`/`pyodbc` driver modules beyond
  stdlib: read `getattr(exc, "sqlite_errorcode", None)` and `exc.args[0]`.
- Docstrings: mention the timeout on each wrapped method.

## ALGORITHM
```
_statement_deadline(conn, seconds, counting):
    stop = monotonic() + seconds
    handler = lambda: int(monotonic() >= min(stop, counting.at if counting and counting.at else stop))
    conn.set_progress_handler(handler, _PROGRESS_STEPS)
    try: yield
    except sqlite3.Error as exc: raise (translate_timeout(exc, seconds) or exc) — use `raise t from exc` when translated, bare `raise` otherwise
    finally: conn.set_progress_handler(None, 0)

translate_timeout(exc, seconds):
    if getattr(exc, "sqlite_errorcode", None) == 9: return QueryTimeoutError(seconds)
    if exc.args and exc.args[0] == "HYT00": return QueryTimeoutError(seconds)
    return None
```

## DATA
- `QueryTimeoutError.seconds: int`; `str(exc)` is exactly
  `Query aborted after N s (statement timeout).`
- `Deadline.at: float | None` (monotonic seconds).

## Tests (write first)
- `tests/backends/test_base_timeout.py` (parametrised): `translate_timeout`
  returns a `QueryTimeoutError` for an exception with `sqlite_errorcode = 9` and
  for one with `args = ("HYT00", "...")`; returns `None` for other codes /
  SQLSTATEs / no args. `str(QueryTimeoutError(30))` matches the message;
  `QueryTimeoutError` is not a `sqlite3.Error`.
- `tests/backends/test_sqlite_timeout.py`, with `query_timeout_seconds=1` and a
  slow recursive CTE (e.g.
  `WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM c) SELECT x FROM c LIMIT 500000000`):
  - `execute_readonly_query` (fresh read-only connection, aborted during fetch)
    raises `QueryTimeoutError` within ~1–3 s;
  - `execute_query` (persistent connection) raises `QueryTimeoutError`;
  - `execute_update` with a slow subquery in `SET` raises `QueryTimeoutError`;
  - after a timeout, a fast query on the persistent connection succeeds (handler
    was cleared);
  - a `Deadline(at=monotonic())` passed to `_statement_deadline` interrupts
    before the statement deadline.
