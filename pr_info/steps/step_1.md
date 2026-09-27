# Step 1 — Schema constraint: `max_rows` must be `>= 1`

Layer 1 of [summary.md](./summary.md). Rejects an out-of-range `max_rows` at the
MCP protocol boundary, before any tool body runs.

## WHERE

- `src/mcp_tools_sql/query_helpers.py` — `build_query_sig_params`, the
  `max_rows` parameter (~lines 104-111)
- `tests/test_query_tools.py` — extend `test_json_schema_generation`
  (~line 182); add one new test after `test_max_rows_hard_clamp` (~line 342)

## WHAT

Signature unchanged:

```python
def build_query_sig_params(config: QueryConfig) -> list[inspect.Parameter]: ...
```

Only the `max_rows` annotation changes:

```python
annotation=Annotated[int, Field(ge=1, description=max_rows_desc)],
```

`Field` is already imported from `pydantic`.

## HOW

`build_query_sig_params` is called by both `query_tools` (configured queries)
and `schema_tools` (built-in schema queries), so this one edit covers every
tool that exposes `max_rows`. The parameter list is attached as a synthesized
`__signature__` by `build_tool_fn` (`tool_builder.py:34`); FastMCP's
`func_metadata` reads it and emits `"minimum": 1` in the published JSON schema.

## ALGORITHM

None — declarative constraint.

## DATA

- Published `inputSchema`: `properties.max_rows` gains `"minimum": 1`.
- A call with `max_rows` of `0` or below returns a `CallToolResult` with
  `isError=True`; the tool body is never entered.

## Tests (write first)

**1. Extend `test_json_schema_generation`** — one line next to the existing
`assert "max_rows" in props`:

```python
assert props["max_rows"]["minimum"] == 1
```

**2. New test — protocol-level rejection.** Existing tests
(`test_query_tools.py:50`, `test_schema_tools.py:355`) call the body directly
and run no pydantic validation, so this one must go through the client session:

```python
@pytest.mark.asyncio
async def test_negative_max_rows_rejected_by_schema(sqlite_db: Path) -> None:
    """max_rows below 1 is rejected by the tool schema, before the body runs."""
```

Build it like `test_max_rows_hard_clamp` (a single `QueryConfig` over
`SELECT id FROM orders`, registered via `QueryTools(*single_target(backend),
queries).register(mcp)`), then assert:

```python
for bad in (-1, 0):
    result = await client.call_tool("query_orders", {"max_rows": bad})
    assert result.isError is True
```

**Important:** open the session as
`create_connected_server_and_client_session(mcp)` — *omit* the
`raise_exceptions=True` used by the neighbouring tests. That flag makes the
low-level server re-raise instead of returning an error result. The
`isError=True` shape above is probe-verified with the default.

## Implementation

Change the annotation at `query_helpers.py:108`. Nothing else.

## Checks

`run_format_code`, `run_pylint_check`, `run_pytest_check` (`["-n", "auto"]`),
`run_mypy_check` — all must pass.

## Commit

```
fix(query): reject max_rows below 1 at the tool schema
```

## LLM prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_1.md`, then implement
> step 1 only. Follow TDD: add the two tests described in the step first, watch
> them fail, then make the one-line annotation change in
> `build_query_sig_params`. Do not touch `_cap_max_rows`, `formatting.py` or
> the verification package — those are later steps. Run
> `run_format_code`, `run_pylint_check`, `run_pytest_check` with
> `extra_args: ["-n", "auto"]` and `run_mypy_check`, then make exactly one
> commit.
