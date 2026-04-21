"""Vulture whitelist - false positives and intentionally kept code.

This file tells Vulture to ignore certain items that appear unused but are
intentionally kept for:
- API completeness (base class methods)
- False positives (pytest fixtures, framework patterns)

Format: _.attribute_name (Vulture's attribute-style whitelist syntax)

Review this list periodically - items may become used or truly dead over time.
"""

# =============================================================================
# FALSE POSITIVES - Pytest Fixtures
# =============================================================================
_.pytestmark
