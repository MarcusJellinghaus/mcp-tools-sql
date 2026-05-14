# Design Decisions — `validate_sql` (issue #8)

Numbered decisions referenced from the step files. Each captures a choice made during plan review and the reason behind it. Decisions are listed in order of capture, not importance.

## Decision #8 — Never re-raise exceptions to the LLM

The `validate_sql` body catches every exception path (specific buckets first, then a `BLE001`-suppressed `except Exception`). The tool always returns a labelled verdict string; it never propagates an exception across the MCP boundary. Rationale: a single, predictable output contract for the LLM caller, with the failure category encoded in the string prefix (`"Invalid SQL. ..."`, `"Invalid parameters. ..."`, `"Database connection error. ..."`, `"Unexpected error. ..."`).

## Decision #9 — Error-message prefix conventions

Pre-flight rejection messages use the synthetic `ValidationError:` prefix (no real Python exception is raised — pre-flight short-circuits before any code path that could raise). Exception-bucketed errors use the real Python `type(exc).__name__` (e.g. `OperationalError:`, `KeyError:`, `RuntimeError:`).

The literal word `Error:` is never used as a bare lead-in — every verdict carries either `ValidationError:` (synthetic, pre-flight) or a concrete Python exception class name (real, post-pre-flight). This keeps the message shape uniform for the LLM and avoids ambiguity about whether the underlying cause was caller-side input or a database / runtime fault.
