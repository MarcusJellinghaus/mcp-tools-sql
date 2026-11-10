# Step 6 — Orchestrator: shared head and `collect_sections` with the `toolset.build` row

## LLM prompt
Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_6.md`.
Write the tests first, then the code. Run `run_format_code`, pylint, pytest
(`extra_args: ["-n", "auto"]`), mypy, ruff, lint-imports, tach and vulture;
all must pass. `verify_all` signature, result types, section order, gating and
CLI output must not change (`verify_snapshot.txt` unchanged). One commit:
`refactor(verification): share head sections; add collect_sections`.

## WHERE
- `src/mcp_tools_sql/verification/orchestrator.py`
- `tests/verification/test_collect_sections.py` (new)

## WHAT
```python
class _Head(NamedTuple):
    sections: list[VerifySection]          # ENVIRONMENT, CONFIG, DEPENDENCIES, BUILTIN
    loaded: LoadedConfigs
    targets: ResolvedTargets | None

def _head_sections(config_path: Path | None, db_config_path: Path | None, project_dir: Path) -> _Head
def _build_row(head_sections: list[VerifySection], build_probe: Callable[[], None]) -> CheckResult
def collect_sections(
    config_path: Path,
    db_config_path: Path | None,
    *,
    connect: bool,
    build_probe: Callable[[], None],
) -> list[VerifySection]
```
`verify_all` calls `_head_sections(...)` and keeps the rest of its body.

## ALGORITHM
```
_build_row:  if not all(s["ok"] for s in head_sections): return make_warn_entry("skipped (earlier errors)")
             try: build_probe()
             except Exception as exc: return make_entry(ok=False, value="failed", error=str(exc))  # pylint: disable=broad-except
             return make_entry(ok=True, value="ok")

collect_sections:
  head = _head_sections(config_path, db_config_path, Path.cwd())
  sections = [*head.sections, _section("TOOLSET", {"build": _build_row(head.sections, build_probe)})]
  if head.targets is None or head.loaded.query_config is None: return sections
  registry = BackendRegistry() if connect else None
  try:
      checks, _default_ok, reachable = _verify_connections(head.targets, registry); append CONNECTION
      append QUERIES verify_queries(qc.queries, head.targets, registry, reachable)   # always, per-target gating
      if registry is not None: append UPDATES verify_updates(qc.updates, head.targets, registry, reachable)
  finally:
      if registry is not None: registry.close_all()
  return sections
```
No INSTALL INSTRUCTIONS section in `collect_sections`. Warnings do not skip the
build row (`section["ok"]` already treats warnings as passing).

## Tests (write first) — `tests/verification/test_collect_sections.py`
Use sqlite configs in `tmp_path` and a recording `build_probe`.
- Order with `connect=False`: ENVIRONMENT, CONFIG, DEPENDENCIES, BUILTIN,
  TOOLSET, CONNECTION, QUERIES; no UPDATES; no `select_1`; no `<q>.sql`.
- `connect=True`, valid sqlite: + `select_1`, `<q>.sql` EXPLAIN ok, UPDATES rows.
- `connect=True`, default connection down (sqlite `path` in a nonexistent
  directory): QUERIES still has `read_only[...]` / `params` / `max_rows_*`
  rows; `<q>.sql` and every UPDATES row is the warning
  "skipped (connection default unreachable)".
- `build_probe` raising `ValueError("boom")` → TOOLSET `build` ERR with error "boom".
- An earlier ERR (e.g. missing explicit db config → CONFIG ERR) → `build` is a
  warning "skipped (earlier errors)" and `build_probe` is not called.
- A head with only warnings (a `password` key in the query config →
  CONFIG `query_config_sensitive_keys` warning) → `build_probe` is still called.
- `verify_all` unchanged: existing orchestrator / CLI tests stay green.

## DATA
`list[VerifySection]`; TOOLSET section `{"build": CheckResult}`.
