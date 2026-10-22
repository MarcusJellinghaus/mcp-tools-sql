# Step 5 — Remove the remaining src asserts (update_tools, summarize)

## LLM prompt
> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_5.md`.
> Do not change `pyproject.toml`. Run the checks listed below, format, and
> make exactly one commit.

## WHERE
- `src/mcp_tools_sql/update_tools.py` — `_build_update_sig_params`,
  `_build_update_body`
- `src/mcp_tools_sql/summarize/tools.py` — value-list block (~lines 475-485)

## WHAT
### update_tools — explicit check instead of asserting
In both `_build_update_sig_params` and `_build_update_body`, replace
`assert config.key is not None` with:

```python
if config.key is None:
    msg = "update config requires a key field"
    raise ValueError(msg)
```
mypy narrows `config.key` after the check, so the rest of each builder is
unchanged. Signatures and the `register()` call sites stay as they are.

Add a `Raises:` section to both docstrings (`DOC501` fires on private
functions too), after `Returns:`:
```
Raises:
    ValueError: If ``config.key`` is missing.
```
Do not add `Args:` sections (the surrounding docstrings don't have them).

### summarize/tools.py — test what the code needs
Replace
```python
if (
    include_distinct
    and view == "deep"
    and meta.category != "other"
    and non_null > 0
):
    # include_distinct plus a non-``other`` category means ...
    assert distinct is not None
    value_kind = ...
```
with
```python
if view == "deep" and distinct is not None and non_null > 0:
    # ``distinct`` is measured only under the row gate and for non-``other``
    # columns, so the shape is a real choice between duplication ("top")
    # and every value unique ("sample").
    value_kind = ...
```
Leave `include_distinct` in place; it still feeds `build_scalar_sql`.

## ALGORITHM
None beyond the substitutions above. Equivalence:
`_split_stats` returns `distinct=None` exactly when the `c{idx}__distinct`
alias was not emitted, i.e. gate off or `other` column; `COUNT(DISTINCT)`
never returns NULL.

## HOW
TDD: behaviour-preserving refactor. Regression coverage:
`tests/test_update_tools.py`, `tests/test_update_tools_multitarget.py`,
`tests/test_server.py`, `tests/summarize/`. No test calls the private
builders directly. The new `raise ValueError` branches are unreachable
(`register()` rejects a missing key first), so per the issue no test is added
for them. Run those first, then the full suite.

## Verification
- `run_ruff_check(select=["S101"], target_directories=["src"])` → clean.
- `run_ruff_check(target_directories=["src","tests","tools"])` → clean.
- mypy `--strict`, pylint, full pytest green.

## Commit
`refactor: replace asserts in update_tools and summarize`
