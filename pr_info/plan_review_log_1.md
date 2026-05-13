# Plan Review Log — Issue #7 (MS SQL Server backend / pyodbc)

## Round 1 — 2026-05-13

**Findings:**
- Step 4 `_sanitize` re-raise used `from None`, losing original traceback.
- Step 4 missing test for `execute_query` with `params=None` and no placeholders.
- Step 4 missing test for `execute_query("SELECT :x", None)` — undefined contract.
- Step 1 missing test that `translate_named_to_qmark` preserves `;` separator in multi-statement SQL.
- Step 2 left removal of unused `import os` in `verify.py` optional — pylint would flag.
- Step 2 did not state explicitly that `_expand_env_vars` walks the entire `DatabaseConfig` dict recursively (incl. `[security]`).
- Step 2 missing test for partial / multiple substitutions in one string (e.g. `${PREFIX}_${SUFFIX}`).
- Step 2 missing test/note that `_SENSITIVE_KEYS` no longer contains `credential_env_var`.
- Step 5 `mssql_db` fixture algorithm attached `_test_schema` to a Pydantic v2 model — rejected by default at runtime.
- Step 6 used `subprocess.run` without listing `import subprocess` in WHERE/HOW imports.
- Step 6 had four near-identical test snippets — no shared `_stub_create_backend` fixture.
- Step 7 docs step vague — no instruction to grep for `credential_env_var` first.
- Open design question: how should unset `${VAR}` errors surface in `verify`?

**Decisions:**
- All straightforward improvements above: **accepted** and applied to plan files.
- Out-of-scope drift: **none found**.
- Empty `TASK_TRACKER.md`: **not a blocker** — populated automatically at step 0 of implementation per planning_principles.md.
- Skipped (not worth the change): empty-password short-circuit on `_sanitize` (overthink), driver-name `}` escaping (controlled by user), darwin equivalent of `klist` non-Linux skip test (already covered by `win32` case), speculative FK-ordering concern in step 5 teardown.

**User decisions:**
- **Q: How should unset `${VAR}` errors surface in `verify`?**
  - **A: Option C** — `_expand_env_vars` raises `ValueError` with a self-describing message including the missing variable name. The existing `database_config_parse` row in `verify`'s CONFIG section surfaces it automatically — no new verify row needed.

**Changes:**
- `pr_info/steps/summary.md` — added recursive expansion note, Option C error-message note, dataclass `MSSQLTestEnv` mention in step 5 row.
- `pr_info/steps/step_1.md` — added `test_translate_preserves_separator_in_multistatement`.
- `pr_info/steps/step_2.md` — Option C clarification + test (error message contains var name); `import os` removal mandatory; partial-substitution test; `_SENSITIVE_KEYS` update note; whole-`DatabaseConfig` recursion scope clarification.
- `pr_info/steps/step_4.md` — `from None` → `from exc`; `params is None` contract section; two new tests.
- `pr_info/steps/step_5.md` — committed to `@dataclass MSSQLTestEnv(config, schema)`; removed Pydantic-attribute-attach alternative.
- `pr_info/steps/step_6.md` — added `import subprocess` to WHERE imports; added shared `_stub_create_backend` fixture; refactored four Kerberos tests onto it.
- `pr_info/steps/step_7.md` — added grep-first instruction for full doc coverage.

**Status:** committed (7 plan files).


## Round 2 — 2026-05-13

**Findings:**
- step_2.md: removal of `import os` in `verify.py` lacked a safety check for other residual `os.` usages.
- step_2.md: Option C unset-`${VAR}` test used a weak regex (`match="MISSING_VAR"`) and had a duplicate assertion.
- step_5.md: seed-data INSERTs were sketched with positional tuples; the backend uses named placeholders, so the tuple form wouldn't compile.
- (Skipped cosmetic items: summary.md wording nod to exact error format; underscore-fixture naming consistency; "in most likelihood" hedge in step 6; docs note on partial substitution.)

**Decisions:**
- Three substantive findings: **accepted** and applied.
- Cosmetic wording polish: **skipped** (default to simpler plans per supervisor guidance).
- No design/requirements questions raised — no user escalation needed this round.

**User decisions:** none.

**Changes:**
- `pr_info/steps/step_2.md` — added residual-`os.` grep safety check before removing `import os`; tightened Option C error-message test to `match=r"\$\{MISSING_VAR\}"`; removed duplicate test.
- `pr_info/steps/step_5.md` — made seed-data INSERTs explicit with named placeholders and dict params for both `customers` and `orders`.

**Status:** committed (2 plan files).

## Final Status

**Rounds completed:** 3.
**Outcome:** Plan ready for approval — Round 3 produced zero plan changes.
**Commits produced:**
- `49f7572` — plan: incorporate supervisor review feedback into steps 1-7
- `9d053e7` — plan: tighten step_2/step_5 — env-var test regex, os-import safety, named INSERT placeholders
- (this commit) — plan: add plan_review_log_1

**Files modified across all rounds:** `pr_info/steps/summary.md`, `step_1.md`, `step_2.md`, `step_4.md`, `step_5.md`, `step_6.md`, `step_7.md`.

**User decisions:**
- Round 1, Q: How should unset `${VAR}` errors surface in `verify`? → **Option C** (self-describing `ValueError` message with the variable name).
