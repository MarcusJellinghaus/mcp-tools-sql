# Step 5 — Remove the remaining src asserts (update_tools, summarize)

## LLM prompt
> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_5.md`.
> Do not change `pyproject.toml`. Run the checks listed below, format, and
> make exactly one commit.

## WHERE
- `src/mcp_tools_sql/update_tools.py` — `_build_update_sig_params`,
  `_build_update_body`, `UpdateTools.register`
- `src/mcp_tools_sql/summarize/tools.py` — value-list block (~lines 475-485)

## WHAT
### update_tools — pass the narrowed key instead of asserting
`register()` already raises `ValueError` when `cfg.key is None`, and mypy
narrows `cfg.key` after it. Hand the narrowed key to the builders:

```python
def _build_update_sig_params(
    config: UpdateConfig, key: UpdateKeyConfig
) -> list[inspect.Parameter]: ...

def _build_update_body(
    name: str,
    config: UpdateConfig,
    key: UpdateKeyConfig,
    qualified: str,
    backend: DatabaseBackend,
) -> Callable[..., Awaitable[str]]: ...
```
- Delete both `assert config.key is not None` lines.
- Inside the builders, replace every `config.key.` with `key.`.
- In `register()`:
  `sig_params = _build_update_sig_params(cfg, cfg.key)` and
  `body = _build_update_body(name, cfg, cfg.key, qualified, backend)`.
- Add `UpdateKeyConfig` to the existing `TYPE_CHECKING` import from
  `mcp_tools_sql.config.models`.
- Docstrings: no `Raises:` needed (nothing raises). Do not add `Args:`
  sections unless the surrounding docstrings already have them (they don't).

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
builders directly. Run those first, then the full suite.

## Verification
- `run_ruff_check(select=["S101"], target_directories=["src"])` → clean.
- `run_ruff_check(target_directories=["src","tests","tools"])` → clean.
- mypy `--strict`, pylint, full pytest green.

## Commit
`refactor: drop asserts in update_tools and summarize via type narrowing`
