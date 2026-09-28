# Summary — Issue #64: uniform row-count gate and corrected `columns=` advice

## Goal

`summarize_columns` has one row-count threshold, `DISTINCT_GATE_ROWS = 1_000_000`,
that governs **both** distinct counts and per-column value lists, in **both**
views. The tool description stops advising the caller to narrow with `columns=`
to save cost — on the table path that advice is backwards. Cross-query
subtraction can no longer print a negative count, and when the underlying counts
disagree the footer says so.

## Architectural / design changes

**1. The gate becomes independent of the view.** Today `tools.py:418-419` chains
two unrelated decisions:

```python
view = "triage" if len(profiled) > TRIAGE_THRESHOLD else "deep"
include_distinct = view == "deep" or rows <= DISTINCT_GATE_ROWS
```

so the row-count gate is dead code in deep mode and which statistics exist
depends on how many columns were named. After the change the gate reads
`rows <= DISTINCT_GATE_ROWS` alone, and the same flag also guards the value-list
pass. Above a million rows: scalar statistics only, N+2 queries collapse to 2.
The visible consequence is a blank distinct cell on every deep block
(`rows N | nulls N (x%) | distinct —`) and no value lists.

**2. Gate messaging leaves the render API.** `distinct_gated` is removed from
`render_summary` and `render_triage`. It was always redundant: the triage cell is
`_BLANK if distinct_gated else _fmt_stat(p.distinct)`, and when the gate fires
`p.distinct` is `None`, which `_fmt_stat` already blanks. The parameter only ever
selected a footer string. That string becomes `distinct_gate_note()` in
`render.py`, joining the existing `empty_source_message` /
`empty_filter_message` / `unknown_columns_message` / `empty_columns_message`
message-builder family, and `tools.py` appends it to the footer list it already
assembles — so the note now reaches the deep view too. The *decision* stays in
`tools.py`; what moves out of the renderers is the flag, not the text.
`DISTINCT_GATE_ROWS` therefore stays in `render.py`, where the builder reads it
through `_fmt_int`.

**3. Renderers stay pure; the pipeline reports the skew.** The pipeline runs
N+2 unsnapshotted queries and the renderer subtracts across them, so
`rows - non_null` and `rows - shown_rows` can go negative. One `_clamp0` helper
in `render.py` floors all three sites at zero. Detection lives in `tools.py` as
a pure predicate `_counts_inconsistent(profile) -> bool` — `ColumnProfile`
already holds every value the five conditions need, so no accumulator threads
through the profile loop and no flag travels back out of a renderer. The footer
gains `inconsistent_counts_note()` only when a condition actually fired, once
per call, naming no columns.

**4. Footer order, fixed in `tools.py`:** `distinct_gate_note()`,
`inconsistent_counts_note()`, `*source.notes`, then `clamp_note` last —
preserving today's placement.

## Non-goals (rejected in the issue; do not add)

Sampling / `sample=` / `detail=`, `APPROX_COUNT_DISTINCT`, a second threshold for
value lists, statement timeout or isolation level (see #61), relocating
`DISTINCT_GATE_ROWS`, renaming the disclosed `sample values (20 of 500,000
distinct …)` header. The residual coupling — below the gate, narrowing 20 columns
to 15 still switches on N value lists — is **accepted and documented**, not a
defect to fix later.

## Files created / modified

| Path | Change |
|---|---|
| `src/mcp_tools_sql/summarize/tools.py` | modified — `_DESCRIPTION` rewritten, module docstring, gate rule, value-list skip, `_counts_inconsistent`, footer assembly |
| `src/mcp_tools_sql/summarize/render.py` | modified — `_clamp0`, `distinct_gate_note`, `inconsistent_counts_note` added; `distinct_gated` removed from both renderers; three arithmetic sites clamped; sample header reworded; stale comments and docstrings corrected |
| `tests/summarize/test_render.py` | modified — `distinct_gated` dropped from ~12 call sites, gate-footer test deleted, sample-header string updated, clamp coverage added |
| `tests/summarize/test_tools.py` | modified — `test_distinct_gate_deep_never_gated` inverted, gate note / value-list-skip / skew-note coverage added |
| `tests/summarize/test_tools_query_source.py` | modified — footer-order coverage carrying both `source.notes` and a clamp note |

No new modules, no new packages, no files deleted. `summarize/sql.py` and
`summarize/source.py` are untouched. `docs/architecture/architecture.md` needs no
change — verified: it describes the summarize package's layering, not the gate.

**Line budget** (limit 750): `render.py` 602 → roughly 620 (three builders added,
the triage footer block removed); `tools.py` 466 → roughly 510. Neither is near
the limit.

## Steps

| Step | Subject |
|---|---|
| [step_1](./step_1.md) | Rewrite `_DESCRIPTION` and the module docstring (documentation only) |
| [step_2](./step_2.md) | `_clamp0` helper, applied at the three cross-query subtraction sites |
| [step_3](./step_3.md) | Reword the `distinct is None` sample header |
| [step_4](./step_4.md) | Move gate messaging out of the render API |
| [step_5](./step_5.md) | Apply the gate uniformly to distinct counts and value lists |
| [step_6](./step_6.md) | `inconsistent_counts_note()` and footer order |

Steps are ordered so every commit leaves the suite green. Step 4 must precede
step 5: the note builder has to exist before the gate starts firing in the deep
view.

## Checks for every step

```
mcp__mcp-tools-py__run_format_code
mcp__mcp-tools-py__run_pylint_check
mcp__mcp-tools-py__run_pytest_check   extra_args: ["-n", "auto"]
mcp__mcp-tools-py__run_mypy_check
```

Also `run_vulture_check` on steps 4 and 6 (a removed parameter and new
module-level functions), and `check_file_size` on the last step.
