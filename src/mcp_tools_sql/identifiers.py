"""Shared SQL identifier whitelist and error formatting.

The pattern and the error wording live here so that both
``update_tools.register`` (Step 4) and ``verify_updates`` (Step 6) reach
for the same source of truth.
"""

from __future__ import annotations

import re

IDENTIFIER_PATTERN: re.Pattern[str] = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def identifier_error(value: str, update_name: str) -> str:
    """Canonical error message for a rejected SQL identifier.

    Args:
        value: The offending identifier string.
        update_name: The name of the update entry that owns the identifier.

    Returns:
        A string suitable for use as the message of a ``ValueError`` or
        as the ``error`` field of a verifier row.
    """
    return (
        f"Invalid identifier {value!r} for update {update_name!r}: must match "
        f"{IDENTIFIER_PATTERN.pattern} (SQL identifiers in mcp-tools-sql are "
        f"intentionally restricted to a strict whitelist)"
    )
