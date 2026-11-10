"""PostgreSQL backend module; for now holds only the psycopg dependency probe."""

from __future__ import annotations


def psycopg_version() -> str:
    """Return psycopg's version string; ``ImportError`` if psycopg is missing.

    Returns:
        ``psycopg.__version__``, or ``""`` when the module does not expose one.
    """
    import psycopg  # pylint: disable=import-error,import-outside-toplevel

    return str(getattr(psycopg, "__version__", ""))
