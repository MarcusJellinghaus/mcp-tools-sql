# Step 4 — Opaque `SourceRef` / `Predicate`; `summarize/source.py` sqlglot-free

See `pr_info/steps/summary.md` for the overall design.

## Kind
Restructure (behaviour-preserving). TDD: tests first.

## WHERE
- `src/mcp_tools_sql/sql_ast/summarize_queries.py` — `SourceRef`, `Predicate` wrappers; builders unwrap.
- New `src/mcp_tools_sql/sql_ast/source_queries.py` — `ParsedSource`, `parse_source`,
  `build_probe_sql`, `source_batch_sql`.
- `src/mcp_tools_sql/summarize/source.py` — no `sqlglot` import left.
- `src/mcp_tools_sql/summarize/tools.py` — type hints only (`predicate: Predicate | None`).
- Tests: new `tests/sql_ast/test_source_queries.py`; edit `tests/summarize/test_source.py`,
  `tests/sql_ast/test_summarize_queries.py`.

## WHAT
```python
# summarize_queries.py  (replaces `SourceRef = exp.Table | exp.Subquery`)
@dataclass(frozen=True)
class SourceRef:
    """What every builder does FROM on: a table or an aliased derived table."""
    _node: exp.Table | exp.Subquery
    def sql(self, dialect: str) -> str: ...      # self._node.sql(dialect=dialect)
    @property
    def is_query(self) -> bool: ...              # isinstance(self._node, exp.Subquery)

@dataclass(frozen=True)
class Predicate:
    """A validated WHERE predicate from validate_where."""
    _node: exp.Expression
    def sql(self, dialect: str) -> str: ...

def build_table_ref(schema, table, dialect) -> SourceRef            # wraps exp.Table
def validate_where(where, table_ref: SourceRef, params, dialect) -> tuple[Predicate | None, str | None]
def build_count_sql(table_ref: SourceRef, predicate: Predicate | None, dialect) -> str
def build_scalar_sql(..., predicate: Predicate | None, ...) -> ...
def build_value_list_sql(..., predicate: Predicate | None, ...) -> ...

# source_queries.py
SOURCE_ALIAS: str = "src"           # moved from summarize/source.py (_SOURCE_ALIAS)

@dataclass(frozen=True)
class ParsedSource:
    ref: SourceRef | None   # None: root is not SELECT / UNION
    row_limited: bool       # TOP / LIMIT / OFFSET present
    order_stripped: bool    # statement ORDER BY removed (no row limit)

@translate_parse_errors
def parse_source(sql: str, dialect: str) -> ParsedSource
def build_probe_sql(ref: SourceRef, rows: int, dialect: str) -> str
def source_batch_sql(ref: SourceRef) -> str          # inner SELECT rendered as tsql
```
`dialect` stays the parameter name of `.sql()` (tests call `ref.sql(dialect=...)`).

## HOW
- Builders: `.from_(table_ref)` → `.from_(table_ref._node)`, and every `table_ref.copy()` →
  `table_ref._node.copy()` (e.g. `build_value_list_sql`'s `.from_(table_ref.copy())` at
  `summarize/sql.py:647` and `:655`; `search_files` for `table_ref.copy()` / `predicate.copy()` to
  catch the rest); `.where(predicate)` → `.where(predicate._node)` (same for any `predicate.copy()`). `validate_where` returns `Predicate(where_clause.this)`.
  (`W0212` protected-access is disabled project-wide; `_node` is accessed only inside `sql_ast`.)
- `summarize/source.py`:
  - delete `import sqlglot`, `from sqlglot import exp`, `_SOURCE_ALIAS`;
  - `exp.Subquery` hints → `SourceRef`;
  - `validate_source` uses `parse_source` (keeps every note/rejection text in `source.py`);
  - `probe_columns`: `probe_sql = build_probe_sql(ref, PROBE_ROWS, dialect)`;
  - `describe_columns`: `substitute_named_with_literals(source_batch_sql(ref), params or {}, "tsql")`.
- `summarize/tools.py`: `_run`'s `predicate: Any` → `Predicate | None` (import from `sql_ast.summarize_queries`).
- `tests/summarize/test_source.py`: `_ref` returns `SourceRef`; `isinstance(ref, exp.Subquery)` →
  `ref.is_query`; `isinstance(built.ref, exp.Table)` → `not built.ref.is_query`; drop the
  `from sqlglot import exp` import (fix the docstring mentioning ``exp.Values`` wording only if needed).
- `tests/sql_ast/test_summarize_queries.py`: wrap any raw `exp` node passed into a builder in
  `SourceRef(...)` / `Predicate(...)`; rendered-SQL assertions stay unchanged.

## ALGORITHM
```
validate_source(sql, params, dialect):
    verdict = basic_preflight(...) or arbitrary_sql_violation(...)   # as today
    if verdict: return (None, [], verdict)
    parsed = parse_source(sql, dialect)
    if parsed.ref is None: return (None, [], ROOT_REJECTION)
    if dialect == "tsql" and has_leading_cte(sql, dialect): return (None, [], LEADING_CTE_REJECTION)
    notes = [ORDER_BY_STRIPPED_NOTE] if parsed.order_stripped else []
    if parsed.row_limited: notes.append(ROW_LIMITED_NOTE)
    return (parsed.ref, notes, None)

parse_source(sql, dialect):
    parsed = sqlglot.parse_one(sql, read=dialect)
    if not isinstance(parsed, (exp.Select, exp.Union)): return ParsedSource(None, False, False)
    row_limited = bool(parsed.args.get("limit") or parsed.args.get("offset"))
    order_stripped = not row_limited and bool(parsed.args.get("order"))
    if order_stripped: parsed.set("order", None)
    return ParsedSource(SourceRef(exp.Subquery(this=parsed, alias=exp.TableAlias(this=exp.to_identifier(SOURCE_ALIAS)))), row_limited, order_stripped)

build_probe_sql(ref, rows, dialect) = exp.select(exp.Star()).from_(ref._node.copy()).limit(rows).sql(dialect=dialect)
source_batch_sql(ref)              = ref._node.this.sql(dialect="tsql")
```

## DATA
Rendered SQL strings identical to today's; `ParsedSource` as above.

## Tests first (`tests/sql_ast/test_source_queries.py`, owner test — may import sqlglot)
- `parse_source("SELECT a FROM t ORDER BY a", "sqlite")`: `ref.is_query`, `order_stripped`,
  not `row_limited`, `ref.sql(dialect="sqlite")` has no `ORDER BY` and ends with `AS src`.
- `TOP 5 ... ORDER BY` (tsql) and `LIMIT 5` (sqlite): `row_limited`, ORDER BY kept.
- `VALUES (1)` / non-query root: `ref is None`.
- `"SELECT 'x"` → `SqlParseError`.
- `build_probe_sql` sqlite → `... LIMIT 5`, tsql → `SELECT TOP 5 * FROM (...) AS [src]`-style
  output equal to `exp.select(exp.Star()).from_(...).limit(5).sql(...)` rendered today (pin the literal).
- `source_batch_sql` returns the inner SELECT only.
- `SourceRef` / `Predicate` are frozen; `build_table_ref(...).is_query is False`.

## Verification
- `search_files` for `sqlglot` in `src/mcp_tools_sql/summarize/` → no match.
- pylint, pytest (`-n auto`), mypy, lint-imports, ruff, `check_file_size` (750) green; format; one commit.

## Commit
`refactor(sql_ast): opaque SourceRef/Predicate and source parsing in sql_ast`

## LLM prompt
> Read `pr_info/steps/summary.md` and `pr_info/steps/step_4.md`. Write
> `tests/sql_ast/test_source_queries.py` first, then make `SourceRef` and `Predicate` opaque
> frozen wrappers in `src/mcp_tools_sql/sql_ast/summarize_queries.py`, create
> `src/mcp_tools_sql/sql_ast/source_queries.py` with `ParsedSource`, `parse_source`,
> `build_probe_sql`, `source_batch_sql`, and remove every sqlglot use from
> `src/mcp_tools_sql/summarize/source.py` and `tests/summarize/test_source.py`. Rendered SQL and
> messages must stay identical. Use MCP tools only. Run pylint, pytest (`-n auto`), mypy,
> lint-imports, ruff and the 750-line file-size check; all must pass. Format, then one commit.
