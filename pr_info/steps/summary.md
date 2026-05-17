# Issue #28 — Config-authoring helpers and per-entry verify

## Goal

Add a small library surface (no new CLI / MCP tools) for:

1. **Authoring `mcp-tools-sql.toml`** programmatically — builders that validate
   via pydantic, plus storage helpers that mutate a `tomlkit.TOMLDocument`
   round-trip-safely.
2. **Per-entry verify primitives** lifted out of the existing bulk loops so
   that future surfaces (CLI `--only <name>`, MCP tool, post-`add_*` validation)
   can validate a single query/update against a live backend without
   re-implementing the per-iteration body.

Neither addition is wired to a user-facing surface in this PR.

---

## Architectural / design changes

### New module: `mcp_tools_sql.config.authoring`

Sits in the existing `config` layer (already a permitted dependency of
`cli.commands` in `tach.toml` and `.importlinter`). **No tach / import-linter
edits required.** `tomlkit` is already an unrestricted project dependency.

Two-layer public API:

| Layer        | Functions                                                     | Purpose                                                                        |
|--------------|---------------------------------------------------------------|--------------------------------------------------------------------------------|
| Construction | `build_query_config`, `build_update_config`                   | Ergonomic kwargs → validated pydantic model. Auto-fill conveniences.           |
| Storage      | `add_query`, `add_update`, `remove_query`, `remove_update`    | Mutate a `tomlkit.TOMLDocument` in place. Round-trip preserving.               |
| Listing      | `list_configured_tools`                                       | Names only, insertion order; missing sections → empty lists (silent).          |

**Why split:** `add_*` takes already-validated models so storage stays a thin
shim; ergonomics live in `build_*`. Adding a non-default model field never
forces a storage-helper change.

### `cli/commands/init.py` refactor

The commented-out example query (`get_user`) and example update
(`set_user_email`) in `_PROJECT_TEMPLATE_STANDALONE` are produced by composing
the two helpers into one fresh `tomlkit.TOMLDocument`, rendering once with
`tomlkit.dumps`, and prefixing each line with `# `. Header / footer remain
static strings. The template is computed once at module load and stored in the
existing `_PROJECT_TEMPLATE_STANDALONE` constant — callers (`init`'s helpers
and the existing tests) see no API change.

### `cli/commands/verify.py` refactor

Extract per-iteration loop bodies of `verify_queries` / `verify_updates` into:

```python
def verify_one_query(name, qcfg, backend_name, backend) -> dict[str, Any]: ...
def verify_one_update(name, ucfg, backend_name, backend) -> dict[str, Any]: ...
```

Return shape: **same per-entry keys as the bulk function emits today, in the
same order**. No `overall_ok`. Variable key count for updates (1 row on
bad-identifier branch; 3 rows on missing-table and happy branches). Bulk
functions become `dict.update(verify_one_*(...))` aggregators that append
`overall_ok` at the end. CLI output is byte-identical — enforced by a snapshot
test scoped to `=== QUERIES ===` + `=== UPDATES ===` sections only.

### KISS decisions applied (vs. naive plan)

- **`max_rows_hard` lean-output rule**: unconditionally drop when equal to
  `max_rows_default`. Escape hatch is `include_defaults=True`. No sentinel
  tracking of "explicitly passed" through builder → storage.
- **Shared private helpers `_add_entry` / `_remove_entry`**: one logic path
  for both query and update siblings.
- **Init template computed once at import time**: `_PROJECT_TEMPLATE_STANDALONE`
  stays a module-level constant; only its initializer changes.
- **Snapshot test = plain checked-in `.txt` fixture**: no snapshot library
  dependency; if the fixture genuinely changes, the maintainer overwrites it
  by hand.
- **Parametrize symmetric tests**: remove `KeyError` family, list-tools
  four cases, params-count variants — each one parametrized test.

---

## Files to create

| Path                                              | Purpose                                     |
|---------------------------------------------------|---------------------------------------------|
| `src/mcp_tools_sql/config/authoring.py`           | Builders + storage helpers + lister         |
| `tests/config/test_authoring.py`                  | Coverage of builders, storage, lister       |
| `tests/cli/fixtures/verify_snapshot.toml`         | Fixture query config used by snapshot test  |
| `tests/cli/fixtures/verify_snapshot.txt`          | Committed `QUERIES`/`UPDATES` byte-snapshot |

## Files to modify

| Path                                              | Change                                                                       |
|---------------------------------------------------|------------------------------------------------------------------------------|
| `src/mcp_tools_sql/cli/commands/init.py`          | `_PROJECT_TEMPLATE_STANDALONE` initialized via `build_* + add_*`.            |
| `src/mcp_tools_sql/cli/commands/verify.py`        | Extract `verify_one_query` / `verify_one_update`; bulk fns become aggregators.|
| `tests/cli/test_init.py`                          | Assert commented-example markers present in generated file.                  |
| `tests/cli/test_verify.py`                        | Per-entry equality tests across all branches + CLI snapshot test.            |

## Files NOT changed

- `tach.toml`, `.importlinter` — new module is inside an already-permitted layer.
- `src/mcp_tools_sql/config/__init__.py` — `authoring` is a sibling module, not
  re-exported (callers import explicitly).
- Public signatures of `verify_queries` / `verify_updates` and their CLI
  behavior — unchanged.
- `pyproject.toml` / dependency manifests — no new project dependencies;
  `tomlkit` and `pydantic` are already top-level.

---

## Implementation steps (one commit each)

1. **Step 1 — Construction builders.** `build_query_config` and
   `build_update_config` in `authoring.py`. TDD-first.
2. **Step 2 — Storage + listing helpers.** `add_*`, `remove_*`,
   `list_configured_tools`. TDD-first.
3. **Step 3 — `init.py` template generation via helpers.** Compute
   `_PROJECT_TEMPLATE_STANDALONE` from `build_* + add_*` at module load.
   Add marker-presence assertion to `test_init.py`.
4. **Step 4 — Per-entry verify extraction + CLI snapshot regression.**
   Extract `verify_one_query` / `verify_one_update`, rewire bulk
   functions to aggregate, add per-entry equality tests across all branches,
   commit the `QUERIES`/`UPDATES` byte-snapshot.

---

## Acceptance gates (run after every step)

- `pytest -x` green.
- `pylint`, `mypy`, `ruff` clean.
- `tach check` and `lint-imports` clean.
- After Step 4: `mcp-tools-sql verify` output for `=== QUERIES ===` +
  `=== UPDATES ===` is byte-identical pre vs. post extraction (enforced by the
  committed snapshot fixture).
