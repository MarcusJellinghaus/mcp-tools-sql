# Step 4 — Move gate messaging out of the render API

`distinct_gated` only ever selected a footer string: the triage cell is
`_BLANK if distinct_gated else _fmt_stat(p.distinct)`, and when the gate fires
`p.distinct` is `None`, which `_fmt_stat` already blanks. Remove the parameter,
keep the text in `render.py` as a message builder, and let `tools.py` append it to
the footer it already assembles — which is also what makes the note reach the deep
view in step 5.

This step must land **before** step 5.

## WHERE

- `src/mcp_tools_sql/summarize/render.py` — new `distinct_gate_note()`;
  `render_triage` and `render_summary` signatures and docstrings; the
  `if distinct_gated:` footer block deleted; the distinct cell simplified.
- `src/mcp_tools_sql/summarize/tools.py` — the `render_summary` call and the
  footer list.
- `tests/summarize/test_render.py` — ~12 call sites lose the argument; one test
  deleted.
- `tests/summarize/test_tools.py` — the gate note's new wording.

## WHAT

**`render.py`**, beside the existing message-builder family (`empty_source_message`
/ `empty_filter_message` / `unknown_columns_message` / `empty_columns_message` /
`column_cap_footer`):

```python
def distinct_gate_note() -> str:
    """Footer note for a source above the row gate.

    One sentence carrying reason and recovery together: the reader who hits the
    gate is looking at the footer, not at the tool description. Source-kind
    neutral -- it says "source", not "table", because a ``sql=`` source hits the
    same gate. Lives here, not in ``tools.py``, so :data:`DISTINCT_GATE_ROWS`
    stays used in its own module and is read through :func:`_fmt_int` rather than
    hardcoded.

    Returns:
        The distinct-gate footer note.
    """
    return (
        f"distinct counts and value lists omitted: the source exceeds "
        f"{_fmt_int(DISTINCT_GATE_ROWS)} rows. "
        "Narrow with where=, or use sql= with a row limit."
    )
```

Exact wording to produce:

```
distinct counts and value lists omitted: the source exceeds 1,000,000 rows.
Narrow with where=, or use sql= with a row limit.
```

(one line — the break above is only this document's wrapping).

Replaces `"distinct omitted: table exceeds 1,000,000 rows."`, which was wrong for
a `sql=` source and no longer covers everything the gate suppresses.

**Signatures:**

```python
def render_triage(profiles: list[ColumnProfile], total_columns: int) -> str: ...
def render_summary(profiles: list[ColumnProfile], total_columns: int) -> str: ...
```

Inside `render_triage`: the cell becomes `"distinct": _fmt_stat(p.distinct)`, and
the trailing `if distinct_gated:` footer append is deleted. `DISTINCT_GATE_ROWS`
stays in `render.py`; it is now read by `distinct_gate_note` instead.

Docstrings: drop the `distinct_gated` argument entry from both, and reword
`render_triage`'s footer paragraph — it currently lists "the row-count reason
distinct was omitted" as a footer it emits. The `columns=` hint paragraph is
**unchanged**; the hint itself stays exactly as written.

**`tools.py`:** call `render_summary(profiles, total_columns)` and build the
footer as

```python
footer: list[str] = []
if not include_distinct:
    footer.append(distinct_gate_note())
footer.extend(source.notes)
if clamp_note:
    footer.append(clamp_note)
```

Import `distinct_gate_note` from `mcp_tools_sql.summarize.render`. Replace the
comment above the footer block — it currently explains that the renderers keep
their signatures, which stops being the point.

Behaviour at this step: triage above the gate prints the new wording in the
footer instead of the old; the deep view is unaffected because `include_distinct`
is still `True` there. Step 5 changes that.

## HOW

Integration points: the `render_summary` call site in `_run`, and the import list
at the top of `tools.py`. Nothing outside the summarize package references these
renderers — confirm with `find_references` on `render_summary` before editing.

## ALGORITHM

```
render_triage(profiles, total_columns):
    rows = [ {name, type, null_pct, _fmt_stat(p.distinct), min, max} for p ]
    footers = [column_cap_footer(...)] if capped else []
    footers.append(the columns= hint, verbatim)
    return table + "\n\n" + "\n".join(footers)
```

## DATA

`distinct_gate_note() -> str`. `render_triage` / `render_summary` still return
`str`. The footer in `tools.py` is a `list[str]` joined with newlines after a
blank line, as today.

## TDD

1. **Delete** `test_triage_gated_blanks_distinct_and_notes_reason`
   (test_render.py:536). It passes `distinct=999` with `distinct_gated=True` — a
   state the pipeline cannot produce — and the blanking it checks is already
   covered by `test_triage_ungated_none_distinct_blanks_without_literal_none`
   (line 646), which builds `distinct=None` and asserts the em dash with no
   literal `None`. Nothing is lost.

2. **Drop the argument** from the remaining `render_summary` / `render_triage`
   call sites: test_render.py lines 488, 494 (**positional** — breaks on the
   signature change), 501, 512, 520, 531, 577, 611, 640, 658.

3. **New**, in `tests/summarize/test_render.py`:

```python
def test_distinct_gate_note_wording() -> None:
    """The gate note states reason and recovery, and names no source kind."""
    note = distinct_gate_note()
    assert note == (
        "distinct counts and value lists omitted: the source exceeds "
        "1,000,000 rows. Narrow with where=, or use sql= with a row limit."
    )
    assert "table" not in note
```

4. **Update** `test_distinct_gate_triage_omits_count_distinct`
   (test_tools.py:362) to assert the new footer text now appears in the output —
   it currently only checks the emitted SQL.

## Commit

`refactor(summarize): move the distinct-gate note out of the render API`

## Checks

`run_format_code`, `run_pylint_check`, `run_pytest_check` with
`extra_args: ["-n", "auto"]`, `run_mypy_check`, and `run_vulture_check` — a
parameter was removed, so check nothing is left unused.

## Prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_4.md`. Implement step 4
> only: add `distinct_gate_note()` to `src/mcp_tools_sql/summarize/render.py`,
> remove the `distinct_gated` parameter from `render_summary` and `render_triage`
> (including their docstrings and the triage footer block), and append the note
> from the `tools.py` footer instead. Keep `DISTINCT_GATE_ROWS` in `render.py` and
> leave the triage `columns=` hint unchanged. Update the tests as the step
> describes, including deleting the redundant one. Do not change the gate rule
> itself — that is step 5. Run format, pylint, pytest (`-n auto`), mypy and
> vulture, then make one commit.
