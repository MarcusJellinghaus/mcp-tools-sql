# Plan Decisions

Decisions from the plan-review discussion for issue #36.

## A. Step 4 (pycycle) scoping — settled empirically

- Ran pycycle locally over the project
  (`pycycle --here --ignore .venv,__pycache__,build,dist,.git,.pytest_cache,.mypy_cache`):
  **no cycles found.**
- Decision: step 4 stays **purely the one `pycycle` matrix-entry line** — no `src/`
  changes expected, and no separate cycle-fix commit is needed. The 5-step structure
  is unchanged (no insert/renumber).
- Guardrail recorded: if a future run ever surfaces a cycle, the fix must be a
  **separate, earlier commit**, never bundled into the CI-config matrix-entry commit.

## B. Step 1 (dev toolchain) — verification hardening

- Decision: before committing, **resolve/install the reshaped `[dev]` set locally**
  (`pip install -e ".[dev]"` or the `uv` equivalent) — do not defer dependency
  resolution to CI. This is in addition to the existing `black --check src tests`
  confirmation.
- Round-2 review: clarified scope — in `mcp-tools-sql.md` only the `pydeps` line is
  removed; the rest of the illustrative/grouped doc block is left as-is and must NOT
  be rewritten to the 4-entry `pyproject.toml` shape (out-of-scope creep).

## C. Summary — step ↔ issue traceability

- Decision: add a one-line note + mapping table to `summary.md` recording that the
  plan's step order intentionally differs from the issue's item numbering (dependency
  change first, matching the issue's "Sequencing" section).
- Mapping (verified against the issue text): step 1 → item 5 (toolchain),
  step 2 → item 3 (no-url-deps), step 3 → item 1 (file-size), step 4 → item 2
  (pycycle), step 5 → item 4 (ruff scope).

## Unchanged (explicitly out of scope for this review)

- Keep the `tests/**/*.py = ["D","DOC"]` ruff per-file-ignore.
- Keep `.large-files-allowlist` non-empty (`mcp-tools-sql.md`).
- Keep file-size as a `test` matrix entry (not a separate job).
- Keep `tools/check_no_url_deps.py` ported verbatim (predicate unchanged).
