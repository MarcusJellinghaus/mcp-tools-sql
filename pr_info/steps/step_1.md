# Step 1 — Type categoriser + package skeleton

Create the `summarize` package and the pure type-classification function that
every later step dispatches on. See `pr_info/steps/summary.md` (§ Architectural
changes #2, § Type categories).

## WHERE

- Create `src/mcp_tools_sql/summarize/__init__.py` (empty for now — no exports
  yet; `SummarizeTools` arrives in step 7).
- Create `src/mcp_tools_sql/summarize/sql.py`.
- Create `tests/summarize/__init__.py` (empty).
- Create `tests/summarize/test_sql.py`.

## WHAT

In `summarize/sql.py`:

```python
Category = Literal["numeric", "temporal", "string", "boolean", "other"]

def categorize_type(declared_type: str, dialect: str) -> Category: ...
```

## HOW

- Pure function, no imports beyond `typing`/`__future__`. Not registered
  anywhere yet; it is exercised only by its unit test this step.
- Matching is **case-insensitive** and **prefix/affinity-based** (SQLite's
  declared type is an arbitrary affinity string, e.g. `VARCHAR(20)`, `NUM`, or
  empty). Do not use exact-match lookup.

## ALGORITHM

```
t = declared_type.strip().lower()
if dialect == "tsql" and t in {"text","ntext","image"}: return "other"   # LOB
if dialect == "tsql" and t in {"timestamp","rowversion"}: return "other" # binary(8)
if t is boolean-like ("bit","bool","boolean"):          return "boolean"
if any int/decimal/float/num/real/money token in t:     return "numeric"
#   `num` (prefix) covers both the bare SQLite affinity `NUM` and `NUMERIC`
if any date/time/timestamp token in t:                  return "temporal"
if any char/text/clob/string token in t OR t == "":     return "string"
return "other"   # binary/blob/varbinary/uniqueidentifier/xml/…
```

Order matters: LOB check before the generic `text` string-token check; the
tsql `timestamp`/`rowversion` guard before the temporal token check;
`boolean` before `numeric` (so `bit` is not swept up by an int token if you
match substrings). Prefer whole-token/prefix matching over naive `in` to avoid
e.g. `timestamp` hitting the `int`… it will not, but keep the token list tidy.

**T-SQL `timestamp` is not temporal.** `INFORMATION_SCHEMA.COLUMNS.DATA_TYPE`
reports `timestamp` for a `rowversion` column, but in T-SQL that is a
`binary(8)` row-version stamp, not a date/time. Left to the `date/time/timestamp`
token rule it would classify as `temporal`, and step 3 would emit
`MIN(c)`/`MAX(c)` — which SQL Server rejects (Msg 8117, *"Operand data type
timestamp is invalid for max operator"*). Because every scalar aggregate shares
one `SELECT`, a single legacy rowversion column would take down the whole
table's scalar pass — exactly the failure mode the LOB guard above exists to
prevent. The guard is **tsql-only**: SQLite's `TIMESTAMP` really is a date/time
affinity and must stay `temporal`.

Both prefix/affinity notes above are load-bearing for the bare SQLite affinity
`NUM`, which the HOW section names as the motivating case: SQLite gives a
`NUM`-declared column NUMERIC affinity, so `NUM` must classify as `numeric`,
not fall through to `other`.

## DATA

Returns one of the five `Category` string literals.

## TESTS (`tests/summarize/test_sql.py`)

Parametrised classification table covering:

- SQLite affinities: `INTEGER`, `INT`, `BIGINT`, `REAL`, `NUMERIC`,
  `NUM` (→ `numeric` — the bare NUMERIC affinity named in HOW; pins that it
  does **not** fall through to `other`), `DECIMAL(10,2)`, `VARCHAR(20)`,
  `TEXT`, `""` (empty → string), `BLOB`, `BOOLEAN`, `DATE`, `DATETIME`.
- T-SQL: `int`, `bigint`, `decimal`, `money`, `float`, `bit`, `nvarchar`,
  `varchar`, `nvarchar(max)` (→ string, **not** other), `datetime2`, `date`,
  `varbinary`, `uniqueidentifier`, and the LOB trio `text`/`ntext`/`image`
  (→ `other`).
- **`timestamp` is dialect-dependent** — assert both directions in one pair:
  `categorize_type("timestamp", "tsql") == "other"` (rowversion = binary(8);
  `MIN`/`MAX` would break the shared scalar `SELECT`) and
  `categorize_type("TIMESTAMP", "sqlite") == "temporal"`. Also
  `categorize_type("rowversion", "tsql") == "other"`.
- Case-insensitivity (`Int`, `VARCHAR`).

## COMMIT

`feat(summarize): add SQL type categoriser and package skeleton`

Run `pylint`, `pytest -n auto`, `mypy` — all green.

## PROMPT

> Implement Step 1 from `pr_info/steps/step_1.md` (context in
> `pr_info/steps/summary.md`). Create the `summarize` package skeleton and a
> pure, prefix/affinity-based `categorize_type(declared_type, dialect)`
> returning the five-value `Category` literal, with LOB (`text`/`ntext`/`image`)
> **and `timestamp`/`rowversion`** classified as `other` on T-SQL — the latter
> is a `binary(8)` row-version, not a date/time, and SQLite's `TIMESTAMP` must
> still classify as `temporal`. The bare SQLite affinity `NUM` classifies as
> `numeric`. Write the parametrised classification test
> first, then the function. Keep it in `summarize/sql.py` — do **not** add a new
> `utils` module. Run pylint, pytest (`-n auto`), and mypy; fix everything
> before committing as one commit.
