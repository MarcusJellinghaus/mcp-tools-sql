"""sqlglot work behind the ``summarize_columns`` ``sql=`` source path.

``summarize/source.py`` owns the gates, messages and column resolution; this
module owns the parsing and rendering it needs, so the caller only ever sees a
:class:`~mcp_tools_sql.sql_ast.summarize_queries.SourceRef` and SQL strings.
The reference is built from the **re-parsed** statement -- the user's raw text
is never concatenated into a later query.
"""

from __future__ import annotations

from dataclasses import dataclass

import sqlglot
from sqlglot import exp

from mcp_tools_sql.sql_ast.placeholders import translate_parse_errors
from mcp_tools_sql.sql_ast.summarize_queries import SourceRef

# Alias given to the derived table wrapping the user's source. Mirrors
# ``count_records``' ``AS count_sub``.
SOURCE_ALIAS: str = "src"


@dataclass(frozen=True)
class ParsedSource:
    """A user source parsed and wrapped as a derived-table reference.

    Attributes:
        ref: The source as ``(<source>) AS src``, or ``None`` when the root is
            not a ``SELECT`` / ``UNION``.
        row_limited: Whether a ``TOP`` / ``LIMIT`` / ``OFFSET`` is present.
        order_stripped: Whether the statement ``ORDER BY`` was removed (only
            when there is no row limit).
    """

    ref: SourceRef | None
    row_limited: bool
    order_stripped: bool


@translate_parse_errors
def parse_source(sql: str, dialect: str) -> ParsedSource:
    """Parse a user SELECT and wrap it as an aliased derived table.

    A statement-level ``ORDER BY`` is stripped when the source carries no row
    limit; with a ``TOP`` / ``LIMIT`` / ``OFFSET`` present it is kept, because
    it then decides which rows survive.

    Args:
        sql: The user's source SQL, already through the read-only gates.
        dialect: sqlglot dialect, ``"sqlite"`` or ``"tsql"``.

    Returns:
        The :class:`ParsedSource`; ``ref`` is ``None`` for a non-query root.
    """
    parsed = sqlglot.parse_one(sql, read=dialect)
    if not isinstance(parsed, (exp.Select, exp.Union)):
        return ParsedSource(ref=None, row_limited=False, order_stripped=False)
    # T-SQL ``TOP``, SQLite ``LIMIT`` and ``OFFSET ... FETCH`` all land in the
    # statement's ``limit`` / ``offset`` args, so one check covers all three.
    row_limited = bool(parsed.args.get("limit") or parsed.args.get("offset"))
    order_stripped = not row_limited and bool(parsed.args.get("order"))
    if order_stripped:
        parsed.set("order", None)
    ref = SourceRef(
        exp.Subquery(
            this=parsed, alias=exp.TableAlias(this=exp.to_identifier(SOURCE_ALIAS))
        )
    )
    return ParsedSource(ref=ref, row_limited=row_limited, order_stripped=order_stripped)


def build_probe_sql(ref: SourceRef, rows: int, dialect: str) -> str:
    """Render ``SELECT * FROM <ref>`` limited to ``rows`` rows.

    Args:
        ref: The source reference to sample.
        rows: Row limit (``LIMIT`` on SQLite, ``TOP`` on T-SQL).
        dialect: sqlglot dialect, ``"sqlite"`` or ``"tsql"``.

    Returns:
        The rendered probe query.
    """
    return (
        exp.select(exp.Star()).from_(ref._node.copy()).limit(rows).sql(dialect=dialect)
    )


def source_batch_sql(ref: SourceRef) -> str:
    """Render the inner SELECT of a derived-table reference as T-SQL.

    Args:
        ref: A query reference from :func:`parse_source`.

    Returns:
        The source statement without the ``(...) AS src`` wrapper.
    """
    inner: exp.Expression = ref._node.this
    return inner.sql(dialect="tsql")
