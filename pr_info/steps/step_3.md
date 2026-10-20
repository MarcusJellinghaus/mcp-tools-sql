# Step 3: dynamic per-tool argument parser (`tool_args.py`)

Read `pr_info/steps/summary.md` first. This step adds a standalone,
unit-tested module that turns one MCP `Tool` into an `argparse.ArgumentParser`
and turns its parsed `Namespace` back into a kwargs dict. It is not yet
wired into `tool.py` (that's step 5) — it's tested directly against `Tool`
objects built via `Tool.from_function`.

**Precondition:** Step 2 is merged. If `src/mcp_tools_sql/cli/commands/tool.py`
does not exist yet, write one line to `pr_info/.blocked.txt` and stop.

## WHERE

- `src/mcp_tools_sql/cli/commands/tool_args.py` (new)
- `tests/cli/test_tool_args.py` (new)

## WHAT

```python
def build_tool_argparser(tool: Tool, prog: str) -> argparse.ArgumentParser: ...
def build_kwargs(ns: argparse.Namespace) -> dict[str, Any]: ...
```

(`Tool` = `mcp.server.fastmcp.tools.base.Tool`.)

## HOW

- Iterate `inspect.signature(tool.fn).parameters.values()` — this is the
  exact signature `build_tool_fn` set as `__signature__`, so it's the same
  source of truth the MCP server itself uses.
- For a parameter literally named `params`: add a repeatable flag,
  `parser.add_argument("--param", dest="params", action="append",
  type=_parse_kv, default=argparse.SUPPRESS, metavar="KEY=VALUE")`, where
  `_parse_kv(s)` splits on the first `=` and raises
  `argparse.ArgumentTypeError` if there isn't one (clean parse-time error,
  exit 2). Values are kept as plain strings — no type inference, matching
  the issue's explicit "no JSON, no comma-separated lists" decision.
- For a parameter literally named `columns`: add
  `parser.add_argument("--column", dest="columns", action="append",
  type=str, default=argparse.SUPPRESS, metavar="NAME")`.
- For every other parameter, unwrap its annotation to find: the base
  scalar type (ignoring `Optional`/`Annotated` wrapping), any `Literal[...]`
  members (→ `choices`), and the `Field` description if present (via the
  `Annotated` metadata) for `help=`. Then:
  - `bool` → `action=argparse.BooleanOptionalAction`
    (`--flag`/`--no-flag`), `default=argparse.SUPPRESS`.
  - `Literal[...]` → `type=str`, `choices=<the literal's args, as str>`,
    `default=argparse.SUPPRESS`.
  - `int` → `type=int`; `float` → `type=float`; everything else
    (`str`, `datetime`) → `type=str` (a malformed `datetime` string is left
    for pydantic to reject at dispatch time — exit 3 — rather than
    duplicating ISO-8601 parsing here).
  - `required=True` only when `param.default is inspect.Parameter.empty`;
    otherwise `required=False`, `default=argparse.SUPPRESS` regardless of
    what the tool's own default value is (including the `_UNSET` sentinel —
    this module never imports or inspects `_UNSET`).
  - Flag name is `f"--{param.name}"`.
- `build_kwargs(ns)` returns `dict(vars(ns))` as-is: because every flag uses
  `default=argparse.SUPPRESS`, an omitted flag is simply absent from `ns`,
  so the dict already contains exactly the keys the caller passed — no
  `_UNSET` bookkeeping needed in this module.

## ALGORITHM

```
build_tool_argparser(tool, prog):
    parser = HelpHintArgumentParser(prog=prog)
    for param in signature(tool.fn).parameters.values():
        if param.name == "params": add repeatable --param KEY=VALUE; continue
        if param.name == "columns": add repeatable --column NAME; continue
        base_type, choices, field_desc = unwrap(param.annotation)
        required = param.default is Parameter.empty
        add_argument(f"--{param.name}", type/action from base_type,
                     choices=choices, required=required,
                     default=SUPPRESS, help=field_desc)
    return parser

build_kwargs(ns):
    return dict(vars(ns))
```

## DATA

`build_kwargs` returns a plain `dict[str, Any]` — scalar values, a `dict`
for `params` (list of `(k, v)` tuples from `--param` is converted to
`dict(...)` here, since `action="append"` with a 2-tuple `type=` yields a
list of tuples), and a `list[str]` for `columns`.

## Tests (write first)

`tests/cli/test_tool_args.py` — build `Tool.from_function(fn)` over small
synthetic functions whose signatures mirror the real shapes (easiest: reuse
`_make_dynamic_tool_fn`-style helpers already in
`tests/test_dynamic_tool_registration.py`, or call `build_tool_fn` directly
with hand-built `inspect.Parameter` lists):

1. A required `str` param → `--name` is required; omitting it is an
   `argparse` error (`SystemExit(2)`).
2. An optional `int` param with a default → omitting `--count` means
   `"count" not in build_kwargs(ns)`; passing `--count 5` yields
   `kwargs["count"] == 5`.
3. A `bool` param → `--flag` / `--no-flag` both work; omitted → absent from
   kwargs.
4. A `Literal["a", "b"]` param → `choices` enforced; a bad value is
   `SystemExit(2)`.
5. A `params: dict[str, Any] | None` param → `--param id=5 --param
   name=foo` → `kwargs["params"] == {"id": "5", "name": "foo"}`; omitted →
   absent from kwargs. A `--param` without `=` → `SystemExit(2)`.
6. A `columns: list[str] | None` param → `--column id --column name` →
   `kwargs["columns"] == ["id", "name"]`; omitted → absent.
7. An `update_*`-shaped optional field (default is the real `_UNSET`
   sentinel object, imported from `tool_builder` only in the test) →
   confirm the built parser still treats it as optional/omittable and the
   module under test never needs to know what the default value *is*.

## Commit

One commit: the tests above, `tool_args.py`, all checks passing.

## LLM prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_3.md`. Implement
> `src/mcp_tools_sql/cli/commands/tool_args.py` exactly as specified:
> `build_tool_argparser` and `build_kwargs`. This module is tested standalone
> against `Tool` objects in this step — do not wire it into `tool.py` yet.
> Write `tests/cli/test_tool_args.py` first, then the implementation. Run
> pylint, pytest, mypy, and ruff checks before committing.
