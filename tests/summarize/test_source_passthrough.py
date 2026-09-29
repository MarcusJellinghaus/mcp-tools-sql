"""Pass-through row-set rejection on the ``summarize_columns(sql=...)`` source.

``validate_source`` re-renders the source from its AST, which preserves an
``OPENQUERY(...)`` call intact, so the AST read-only proof alone would still
ship the embedded statement to the linked server.
"""

from __future__ import annotations

import pytest

from mcp_tools_sql.summarize.source import validate_source

_PASSTHROUGH = [
    ("SELECT * FROM OPENQUERY(srv, 'DELETE FROM t')", "OPENQUERY"),
    ("SELECT * FROM OPENROWSET('SQLNCLI', 'srv', 'DELETE FROM t')", "OPENROWSET"),
    (
        "SELECT * FROM OPENDATASOURCE('SQLNCLI', 'Server=s').db.dbo.t",
        "OPENDATASOURCE",
    ),
]


@pytest.mark.parametrize(("sql", "function"), _PASSTHROUGH)
@pytest.mark.parametrize("dialect", ["sqlite", "tsql"])
def test_passthrough_sources_rejected(sql: str, function: str, dialect: str) -> None:
    """A linked-server pass-through never becomes a derived table."""
    ref, notes, error = validate_source(sql, None, dialect)

    assert ref is None
    assert notes == []
    assert error is not None
    assert error.startswith("Not read-only.")
    assert function in error


@pytest.mark.parametrize("dialect", ["sqlite", "tsql"])
def test_column_named_openquery_is_accepted(dialect: str) -> None:
    """A column merely *named* ``openquery`` is an identifier, not a call."""
    ref, _notes, error = validate_source("SELECT openquery FROM t", None, dialect)

    assert error is None
    assert ref is not None
