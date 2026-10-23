# Step 3 — CI coverage wiring

## LLM prompt
> Read `pr_info/steps/summary.md`, then implement **only** `pr_info/steps/step_3.md`.
> Edit `.github/workflows/ci.yml` as described: add the `unit-tests` job, add
> `--cov` flags and uploads to the three integration jobs, and add the `coverage`
> job. First run the guard probe. Then run the checks, format, and make exactly
> one commit.

## WHERE
- `.github/workflows/ci.yml` (only file changed)
- `.scratch/test_probe.py` (temporary; deleted before commit)

## Precondition — guard probe
The `coverage` job's no-data guard relies on `coverage combine` exiting non-zero
for a **missing** and an **empty** directory. Probe it with a scratch test,
following the "Scratch probes" section of CLAUDE.md. In `tmp_path`, run
`subprocess.run([sys.executable, "-m", "coverage", "combine", <dir>])` for a
non-existent dir and for an empty dir, and assert `returncode != 0` for both. Run it
with `run_pytest_check` and `extra_args: ["-p", "no:cacheprovider", ".scratch/test_probe.py"]`,
then `delete_directory(".scratch", recursive=True)`.
- Both non-zero → use the guard below as written.
- Otherwise → put `[ -n "$(ls -A coverage-data 2>/dev/null)" ] &&` in front of
  `coverage combine` inside the guard condition.
- If `coverage` is not importable in the environment, write one line to
  `pr_info/.blocked.txt` (`coverage not installed; cannot probe combine exit codes`)
  and stop.

## WHAT

### 1. `test` matrix
Remove the `pytest` entry.

### 2. New `unit-tests` job (after the `test` job)
Same checkout / uv / Python 3.11 / install steps as the `test` job (install `.[dev]`).
```yaml
      - name: Run unit tests
        env:
          COVERAGE_FILE: .coverage.unit
        run: pytest --version && pytest tests -m 'not sqlite_integration and not mssql_integration and not postgresql_integration' --cov=src/mcp_tools_sql --cov-report=

      - name: Upload coverage data
        if: always()
        uses: actions/upload-artifact@v7
        with:
          name: coverage-data-unit
          path: .coverage.unit
          include-hidden-files: true
          retention-days: 1
```

### 3. Integration jobs (`sqlite-integration`, `postgresql-integration`, `mssql-integration`)
In each run step, append `--cov=src/mcp_tools_sql --cov-report=` to the
`pytest ... -v` command inside the existing `rc=0; ... || rc=$?` wrapper. Also
add `COVERAGE_FILE` to the step `env` (create an `env:` block for sqlite):
`.coverage.sqlite`, `.coverage.postgresql` or `.coverage.mssql`. Then append:
```yaml
      - name: Upload coverage data
        if: always()
        uses: actions/upload-artifact@v7
        with:
          name: coverage-data-<sqlite|postgresql|mssql>
          path: .coverage.<sqlite|postgresql|mssql>
          include-hidden-files: true
          if-no-files-found: ignore
          retention-days: 1
```

### 4. New `coverage` job (after `mssql-integration`)
```yaml
  # Coverage report (reporting only — never a gate)
  coverage:
    runs-on: ubuntu-latest
    needs: [unit-tests, sqlite-integration, postgresql-integration, mssql-integration]
    if: always() && (github.event_name == 'pull_request' || github.ref == 'refs/heads/main')
    steps:
      - uses: actions/checkout@v7
        with:
          fetch-depth: 0

      - name: Set up Python 3.11
        uses: actions/setup-python@v6
        with:
          python-version: 3.11

      - name: Install coverage tools
        run: pip install coverage diff-cover

      - name: Download coverage data
        continue-on-error: true
        uses: actions/download-artifact@v8
        with:
          pattern: coverage-data-*
          path: coverage-data
          merge-multiple: true

      - name: Coverage report
        run: |
          if ! { coverage combine coverage-data && coverage xml -o coverage.xml; }; then
            echo "_No coverage data for this run; coverage report skipped._" >> "$GITHUB_STEP_SUMMARY"
            exit 0
          fi
          if [ "${{ github.event_name }}" = "pull_request" ]; then
            diff-cover coverage.xml \
              --compare-branch=origin/${{ github.base_ref }} \
              --format markdown:diff-coverage.md || true
          fi
          args=(--coverage-xml coverage.xml --output "$GITHUB_STEP_SUMMARY")
          if [ -f diff-coverage.md ]; then args+=(--diff-report diff-coverage.md); fi
          python tools/ci_coverage_summary.py "${args[@]}"
```

## HOW
- Action versions match the existing file (`checkout@v7`, `setup-uv@v7` with
  `enable-cache: false`, `setup-python@v6`). The artifact actions use mcp_coder's
  versions (`upload-artifact@v7`, `download-artifact@v8`).
- `pytest-cov` comes from the `dev` extra (step 2). `-n auto` comes from `addopts`.
- `src/` is measured, not site-packages, because of `pythonpath = ["src"]`.

## ALGORITHM (coverage step)
```
if combine fails or xml fails (no/empty data, "No data to report"):
    write notice to step summary; exit 0
if PR: diff-cover vs origin/<base> → diff-coverage.md (ignore failure)
run ci_coverage_summary.py → append to step summary (+ diff report if present)
```

## DATA
- Artifacts: `coverage-data-{unit,sqlite,postgresql,mssql}`, each containing one
  `.coverage.<name>` file, kept for 1 day.
- Step summary: the coverage Markdown from step 2, or the one-line notice.

## Verification
1. Check the YAML by reading it back. Make sure the indentation matches the
   neighbouring jobs, every `needs` name exists, and no `pytest` entry is left in
   the `test` matrix.
2. Run `run_pylint_check`, `run_mypy_check`, and `run_pytest_check` with
   `extra_args: ["-n", "auto"]`. All must pass.
3. Make sure `.scratch/` is deleted. Run `run_format_code`, then commit:
   `ci: report combined coverage from unit and integration jobs`.
