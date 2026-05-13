# Step 1 — Foundations: sqlparse + `utils/sql_placeholders.py` + delegation

## Goal

Introduce a tokenizer-aware module that recognizes `:name` placeholders in
SQL while **ignoring** placeholders inside quoted strings (`'…'`, `"…"`) and
comments (`-- …`, `/* … */`). Use it from `query_helpers.extract_sql_params`
so verify and the future MSSQL `:name → ?` translator agree on edge cases.

## WHERE

| Action | Path |
|---|---|
| Create | `src/mcp_tools_sql/utils/sql_placeholders.py` |
| Modify | `src/mcp_tools_sql/query_helpers.py` (delegate `extract_sql_params`) |
| Modify | `pyproject.toml` (add `sqlparse>=0.5` to `[project.dependencies]`) |
| Create | `tests/test_sql_placeholders.py` |

## WHAT

```python
# src/mcp_tools_sql/utils/sql_placeholders.py
from __future__ import annotations

def extract_param_names(sql: str) -> set[str]: ...
def translate_named_to_qmark(sql: str) -> tuple[str, list[str]]: ...
```

- `extract_param_names(sql)` — returns the **set** of `:name` placeholder
  names that are **not** inside quoted strings or comments.
- `translate_named_to_qmark(sql)` — returns a 2-tuple
  `(translated_sql, ordered_names)` where every placeholder has been
  rewritten as `?` and `ordered_names[i]` is the name of the *i*-th `?`.

`query_helpers.extract_sql_params` becomes a one-liner that calls
`extract_param_names`.

## HOW

- Use `sqlparse.parse(sql)` → iterate statements → `stmt.flatten()` for a
  flat token stream.
- Filter on `token.ttype is sqlparse.tokens.Name.Placeholder` **and**
  `token.value.startswith(":")` (sqlparse tags placeholders distinctly from
  string-literal and comment tokens, so quoted-string and comment placeholders
  are automatically skipped — no manual state machine needed).
- The translator walks the same flat token stream once, accumulating either
  the original token text or `"?"`.

## ALGORITHM

```
def _iter_placeholders(sql):
    for stmt in sqlparse.parse(sql):
        for tok in stmt.flatten():
            if tok.ttype is Name.Placeholder and tok.value.startswith(":"):
                yield tok                # token, so caller can read .value

def extract_param_names(sql):
    return {t.value[1:] for t in _iter_placeholders(sql)}

def translate_named_to_qmark(sql):
    names, parts = [], []
    for stmt in sqlparse.parse(sql):
        for tok in stmt.flatten():
            if tok.ttype is Name.Placeholder and tok.value.startswith(":"):
                names.append(tok.value[1:]); parts.append("?")
            else:
                parts.append(tok.value)
    return "".join(parts), names
```

## DATA

- `extract_param_names`: `set[str]` (unordered, deduplicated).
- `translate_named_to_qmark`: `tuple[str, list[str]]` — list **preserves order
  and duplicates** (one entry per `?` in the rewritten SQL).

## Tests (write FIRST)

`tests/test_sql_placeholders.py`:

```python
class TestExtractParamNames:
    def test_basic(): ":a AND :b" → {"a", "b"}
    def test_inside_single_quotes(): "WHERE x = ':a'" → set()
    def test_inside_double_quotes(): 'WHERE "x:a" = 1' → set()
    def test_inside_line_comment(): "SELECT 1 -- :a" → set()
    def test_inside_block_comment(): "SELECT 1 /* :a */" → set()
    def test_repeated_name(): ":a + :a" → {"a"}
    def test_multi_statement(): ":a; SELECT :b" → {"a", "b"}
    def test_no_placeholders(): "SELECT 1" → set()

class TestTranslateNamedToQmark:
    def test_basic(): "SELECT :a, :b" → ("SELECT ?, ?", ["a", "b"])
    def test_repeated_name(): "WHERE x = :a OR y = :a" →
        ("WHERE x = ? OR y = ?", ["a", "a"])
    def test_inside_string_untouched(): "SELECT ':a' WHERE x = :b" →
        ("SELECT ':a' WHERE x = ?", ["b"])
    def test_inside_comment_untouched(): "SELECT :a -- :b\nFROM t" →
        ("SELECT ? -- :b\nFROM t", ["a"])
    def test_no_placeholders(): roundtrip unchanged, empty list.
```

`tests/test_query_tools.py` (or wherever `extract_sql_params` is exercised) — add:

```python
def test_extract_sql_params_skips_string_literal():
    # delegation guarantee
    assert extract_sql_params("SELECT ':foo' AS x WHERE id = :bar") == {"bar"}
```

## Checks

- `mcp__tools-py__run_pylint_check`
- `mcp__tools-py__run_mypy_check`
- `mcp__tools-py__run_pytest_check(extra_args=["-n", "auto", "-m", "not git_integration and not claude_cli_integration and not claude_api_integration and not formatter_integration and not github_integration and not langchain_integration"])`
- Format with `./tools/format_all.sh`
- Single commit: tests + implementation + dep bump.

## LLM Prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_1.md`. Implement
> Step 1 exactly as specified: add `sqlparse>=0.5` to core deps, create
> `src/mcp_tools_sql/utils/sql_placeholders.py` with `extract_param_names`
> and `translate_named_to_qmark`, delegate `query_helpers.extract_sql_params`
> to it, and write the tests in `tests/test_sql_placeholders.py` first
> (TDD). Run pylint, mypy, and pytest via the MCP tools per CLAUDE.md
> after every edit. End with a single commit.
