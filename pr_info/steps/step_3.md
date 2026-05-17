# Step 3 — `init.py` template generation via helpers

**Prompt for LLM:**
> Read `pr_info/steps/summary.md` and then implement `pr_info/steps/step_3.md`.
> Steps 1 and 2 are already merged — the builders and storage helpers exist.
> TDD: write the new marker test in `test_init.py` first, run it green
> (passes today because the static template happens to contain those
> strings), then replace the static example block with helper-generated
> content; the test must still pass. Finish by running pylint, mypy, ruff,
> tach, and import-linter — all must be clean. One commit.

---

## WHERE

- **Modify (impl):** `src/mcp_tools_sql/cli/commands/init.py`.
- **Modify (tests):** `tests/cli/test_init.py` — add one marker-presence test.

## WHAT

In `init.py`, replace the hard-coded example query / update lines inside
`_PROJECT_TEMPLATE_STANDALONE` with content computed at module load time
from the Step 1 / Step 2 helpers. The constant name stays the same so all
callers (`_build_project_template_standalone` and any existing tests) are
untouched.

```python
def _build_query_block() -> str: ...      # private, runs once at import
def _build_update_block() -> str: ...     # private, runs once at import
```

`_PROJECT_TEMPLATE_STANDALONE` is assembled by concatenating the static
SELECT header, the rendered query block, a blank separator, the static
UPDATE header, the rendered update block, and the static footer. This
preserves today's UX exactly: the `# Example UPDATE definition` header
sits BETWEEN the queries block and the updates block (not above both).

## HOW

- Import: `import tomlkit` is already present.
- Import: `from mcp_tools_sql.config.authoring import build_query_config,
  build_update_config, add_query, add_update`.
- Tach: `mcp_tools_sql.cli.commands` already depends on
  `mcp_tools_sql.config`. No tach edits.

## ALGORITHM

Shared helper (inline, or a private `_render_commented(doc) -> str`):
```
rendered = tomlkit.dumps(doc)
return "\n".join(f"# {line}" if line else "#" for line in rendered.splitlines()) + "\n"
```

`_build_query_block()` (runs once at import time):
```
doc = tomlkit.document()
qcfg = build_query_config(
    "get_user",
    description="Look up a user by id",
    sql="SELECT * FROM users WHERE id = :id",
    params={"id": {"type": "int", "description": "User id", "required": True}},
    max_rows_default=1,
)
add_query(doc, "get_user", qcfg)
return _render_commented(doc)
```

`_build_update_block()` (runs once at import time):
```
doc = tomlkit.document()
ucfg = build_update_config(
    "set_user_email",
    description="Update a user's email",
    schema="dbo",
    table="users",
    key={"field": "id", "type": "int", "description": "User id"},
    fields=[{"field": "email", "type": "str", "description": "New email"}],
)
add_update(doc, "set_user_email", ucfg)
return _render_commented(doc)
```

Notes:
- Use `f"# {line}"` for non-empty lines and `"#"` for blank lines so the
  result remains valid commented-out TOML (the issue allows `"# "` with
  trailing space — pick the variant that keeps black/ruff happy; both parse
  the same when uncommented).
- Building each block from its own fresh `TOMLDocument` keeps the two blocks
  visually separated (one trailing newline each) and lets the static
  `# Example UPDATE definition (uncomment to enable):` header sit naturally
  between them — matching today's UX.

Concrete split of the existing constant:
- `_HEADER` ends just after `"# Example SELECT query (uncomment to enable):\n"`.
- `_MIDDLE` is the single line
  `"# Example UPDATE definition (uncomment to enable):\n"`.
- `_FOOTER` begins at `"# Default schema-introspection queries auto-load..."`.

Final assembly:

```
_PROJECT_TEMPLATE_STANDALONE = (
    _HEADER                       # connection line + first blank + SELECT header
    + _build_query_block()
    + "\n"
    + _MIDDLE                     # UPDATE header line
    + _build_update_block()
    + "\n"
    + _FOOTER                     # default-queries pointer block
)
```

## DATA

`_build_query_block()` and `_build_update_block()` each return `str`. The
full `_PROJECT_TEMPLATE_STANDALONE` constant remains a `str` with the same
trailing newline behavior as today.

## Tests

Add to `tests/cli/test_init.py`:

```python
def test_init_template_contains_example_markers(tmp_path: Path) -> None:
    """Generated mcp-tools-sql.toml still contains commented example markers."""
    output = tmp_path / "mcp-tools-sql.toml"
    rc = init_cmd.run(_make_args("sqlite", output=output))
    assert rc == 0
    text = output.read_text(encoding="utf-8")
    assert "# [queries.get_user]" in text
    assert "# [updates.set_user_email]" in text
```

The existing `test_init_generates_valid_toml` test continues to enforce
`tomllib`-parse cleanliness. Every other existing test in `test_init.py`
must continue to pass without modification.

Run gates:
- `pytest tests/cli/test_init.py -x`
- Full `pytest -x` to confirm no regressions elsewhere.
- `pylint`, `mypy`, `ruff`, `tach check`, `lint-imports`.
