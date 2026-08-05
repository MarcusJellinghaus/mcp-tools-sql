# Step 3 — Bump the sqlglot floor to `>=30`

> Read `pr_info/steps/summary.md` first. This step implements item 3 of the
> issue. Independent config change. One commit.

## Rationale

The read-only security gate reads sqlglot's AST directly (`_WRITE_NODES`,
`_READONLY_ROOTS`, the `with_`/`with` fallback in `_has_leading_cte`) — all
version-sensitive, and `with_` is not guaranteed by a `>=25` floor. Verified
present on sqlglot 30.15.0; sqlglot 30 declares `Requires-Python >=3.9`, and the
project is `>=3.11`, so the bump is safe. No upper bound — caps cause resolver
conflicts downstream.

## WHERE

- `pyproject.toml`, `dependencies` list (line 30).

## WHAT

```
"sqlglot>=25",   ->   "sqlglot>=30",
```

## HOW

Config-only. The "test" is that the **existing** suite (which already resolves
the newest sqlglot via `uv pip install --system ".[dev]"`) stays green — the
version-sensitive gate code is exercised by the current read-only and
leading-CTE tests. Do **not** remove the dead `_has_leading_cte` `"with"`
fallback (kept deliberately). Do not add an upper bound. No new CI job.

## ALGORITHM / DATA

None.

## Gates

`run_pytest_check` (full/marker-excluded per CLAUDE.md), `run_pylint_check`,
`run_mypy_check` — all green, confirming the floor bump breaks nothing.

## LLM prompt

> Implement Step 3 from `pr_info/steps/step_3.md` (context in
> `pr_info/steps/summary.md`). In `pyproject.toml`, change the dependency
> `"sqlglot>=25"` to `"sqlglot>=30"` with no upper bound. Do not touch the
> `_has_leading_cte` fallback or add a CI job. Confirm the existing test suite
> stays green. One commit.
