# Step 3: `format_rows()` Implementation

## Context
See [summary.md](./summary.md) for full issue context. This step implements the result formatting function that all config-driven tools will use for output.

## LLM Prompt
> Implement step 3 of issue #4 (see `pr_info/steps/summary.md` and `pr_info/steps/step_3.md`).
> Implement `format_rows()` in `formatting.py` using `tabulate`. TDD: write tests first, then implementation. Handle truncation, empty results, and the truncation warning message.

### WHERE
- `tests/test_formatting.py` (new file, tests first)
- `src/mcp_tools_sql/formatting.py`

### WHAT — Updated signature
```python
def format_rows(
    rows: list[dict[str, Any]],
    max_rows: int = 100,
) -> str:
    """Format query result rows as LLM-friendly tabular text.

    Args:
        rows: Query result rows as list of dicts.
        max_rows: Maximum rows to display. If len(rows) > max_rows,
                  output is truncated with a warning message.

    Returns:
        Formatted table string with column headers.
    """
```

Note: the current signature has `total_count` param — simplify to just derive it from `len(rows)`. The function receives all rows and truncates internally.

### ALGORITHM
```
if not rows:
    return "No results found."
total = len(rows)
display_rows = rows[:max_rows]
table = tabulate(display_rows, headers="keys", tablefmt="simple")
if total > max_rows:
    table += f"\n\nShowing {max_rows} of {total} rows. Use filter to narrow."
return table
```

### DATA — Return format
```
name    type     nullable    default    is_primary_key
------  -------  ----------  ---------  ----------------
id      INTEGER  False       None       True
name    TEXT     True        None       False
```

### WHAT — Tests (`tests/test_formatting.py`)
```python
class TestFormatRows:
    def test_basic_table(self) -> None:
        """Formats rows as tabular text with column headers."""

    def test_empty_rows(self) -> None:
        """Returns 'No results found.' for empty list."""

    def test_single_row(self) -> None:
        """Single row formats correctly."""

    def test_truncation_at_max_rows(self) -> None:
        """Rows beyond max_rows are truncated with warning message."""

    def test_truncation_message_text(self) -> None:
        """Warning includes actual count and max_rows."""

    def test_no_truncation_at_boundary(self) -> None:
        """Exactly max_rows rows → no truncation message."""

    def test_column_headers_from_dict_keys(self) -> None:
        """Column headers come from dict keys of first row."""
```

### HOW — Integration points
- `tabulate` is already a dependency in `pyproject.toml`
- `tablefmt="simple"` for clean LLM-readable output (no markdown pipes)
- Leave `format_columns()` and `format_update_result()` stubs untouched — they're for future issues

### HOW — Verify
- All formatting tests pass
- All existing tests still pass
- mypy, pylint pass
