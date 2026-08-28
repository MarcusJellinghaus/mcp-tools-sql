"""Tests for the sql_placeholders module (sqlglot-based).

These tests both exercise the public helpers and *gate the make-or-break
spike*: that sqlglot parses ``:name`` into a concrete
:class:`sqlglot.exp.Placeholder` node whose ``.name`` is the bare name.
Because the helpers re-render through sqlglot's generator, assertions on
incidental formatting (dropped comments, keyword casing) are kept
semantic; the names list and placeholder positions are asserted exactly.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
import sqlglot
from sqlglot import exp

from mcp_tools_sql.utils.sql_placeholders import (
    LEADING_CTE_REJECTION,
    build_count_query,
    extract_param_names,
    has_leading_cte,
    read_only_violation,
    substitute_named_with_literals,
    translate_named_to_qmark,
)


class TestPlaceholderNodeSpike:
    """Empirically confirm sqlglot's placeholder node type and ``.name``."""

    def test_named_placeholder_is_placeholder_node(self) -> None:
        parsed = sqlglot.parse_one("SELECT :name")
        placeholders = list(parsed.find_all(exp.Placeholder))
        assert len(placeholders) == 1
        node = placeholders[0]
        assert isinstance(node, exp.Placeholder)
        # The bare name (no leading ":") is exposed via ``.name``.
        assert node.name == "name"

    def test_anonymous_placeholder_has_empty_name(self) -> None:
        parsed = sqlglot.parse_one("SELECT ?")
        placeholders = list(parsed.find_all(exp.Placeholder))
        assert len(placeholders) == 1
        # ``?`` parses to a placeholder carrying no ``this`` arg. sqlglot's
        # ``.name`` falls back to "?" for it, so named-ness is distinguished
        # via ``text("this")`` (empty here), not ``.name``.
        assert placeholders[0].text("this") == ""
        assert placeholders[0].name == "?"


class TestExtractParamNames:
    """Tests for ``extract_param_names``."""

    def test_basic(self) -> None:
        assert extract_param_names("SELECT :a AND :b") == {"a", "b"}

    def test_inside_single_quotes(self) -> None:
        assert extract_param_names("SELECT * FROM t WHERE x = ':a'") == set()

    def test_inside_double_quotes(self) -> None:
        assert extract_param_names('SELECT * FROM t WHERE "x:a" = 1') == set()

    def test_inside_line_comment(self) -> None:
        assert extract_param_names("SELECT 1 -- :a") == set()

    def test_inside_block_comment(self) -> None:
        assert extract_param_names("SELECT 1 /* :a */") == set()

    def test_repeated_name(self) -> None:
        assert extract_param_names("SELECT :a + :a") == {"a"}

    def test_multi_statement(self) -> None:
        assert extract_param_names("SELECT :a; SELECT :b") == {"a", "b"}

    def test_no_placeholders(self) -> None:
        assert extract_param_names("SELECT 1") == set()


class TestTranslateNamedToQmark:
    """Tests for ``translate_named_to_qmark``."""

    def test_basic(self) -> None:
        assert translate_named_to_qmark("SELECT :a, :b") == (
            "SELECT ?, ?",
            ["a", "b"],
        )

    def test_repeated_name(self) -> None:
        sql_out, names = translate_named_to_qmark(
            "SELECT * FROM t WHERE x = :a OR y = :a"
        )
        assert names == ["a", "a"]
        assert sql_out.count("?") == 2
        assert ":a" not in sql_out

    def test_inside_string_untouched(self) -> None:
        sql_out, names = translate_named_to_qmark("SELECT ':a' AS s, :b")
        # The ``:a`` inside the string literal is not a placeholder.
        assert names == ["b"]
        assert sql_out.count("?") == 1
        assert "':a'" in sql_out

    def test_inside_comment_untouched(self) -> None:
        # sqlglot reformats/relocates comments; ``:b`` inside the comment is
        # never a placeholder, so only ``:a`` is translated.
        sql_out, names = translate_named_to_qmark("SELECT :a -- :b\nFROM t")
        assert names == ["a"]
        assert sql_out.count("?") == 1

    def test_no_placeholders(self) -> None:
        sql_out, names = translate_named_to_qmark("SELECT 1 FROM dual")
        assert names == []
        assert sql_out == "SELECT 1 FROM dual"

    def test_translate_preserves_separator_in_multistatement(self) -> None:
        sql_out, names = translate_named_to_qmark("SELECT :a; SELECT :b")
        assert sql_out == "SELECT ?; SELECT ?"
        assert names == ["a", "b"]

    def test_roundtrip_single_named_placeholder(self) -> None:
        # Make-or-break round-trip: a single ``:name`` must survive parse +
        # render as a bindable placeholder, and stay extractable by name.
        assert extract_param_names("SELECT :a") == {"a"}
        sql_out, names = translate_named_to_qmark("SELECT :a")
        assert names == ["a"]
        assert "?" in sql_out
        # The rendered ``?`` is itself a bindable anonymous placeholder.
        reparsed = sqlglot.parse_one(sql_out)
        anon = list(reparsed.find_all(exp.Placeholder))
        assert len(anon) == 1
        assert anon[0].text("this") == ""

    def test_ordered_multi_placeholder_roundtrip(self) -> None:
        # The ``:name`` -> ``?`` positional order must match the source order.
        sql_out, names = translate_named_to_qmark(
            "SELECT * FROM t WHERE a = :x AND b = :y"
        )
        assert names == ["x", "y"]
        assert sql_out.count("?") == 2

    def test_tsql_preserves_bracket_quoting(self) -> None:
        # Under the tsql dialect, bracket-quoted identifiers ``[id]`` must
        # survive parse+render unchanged. The dialect-neutral renderer would
        # corrupt ``[id]`` into ``ARRAY(id)``; ``dialect="tsql"`` prevents it.
        sql_out, names = translate_named_to_qmark(
            "SELECT [id], [name] FROM dbo.[orders] WHERE [id] = :id", "tsql"
        )
        assert names == ["id"]
        assert "[id]" in sql_out
        assert "[name]" in sql_out
        assert "[orders]" in sql_out
        assert "ARRAY(" not in sql_out
        assert sql_out.count("?") == 1

    def test_tsql_bracketed_sql_parses_without_error(self) -> None:
        # A bracket-quoted statement must parse cleanly under the tsql dialect.
        sql_out, names = translate_named_to_qmark(
            "SELECT * FROM [orders] WHERE id = :id", "tsql"
        )
        assert names == ["id"]
        assert "[orders]" in sql_out


class TestSubstituteNamedWithLiterals:
    """Tests for ``substitute_named_with_literals``."""

    def test_int(self) -> None:
        assert substitute_named_with_literals("SELECT :a", {"a": 1}) == "SELECT 1"

    def test_negative_int(self) -> None:
        assert substitute_named_with_literals("SELECT :a", {"a": -7}) == "SELECT -7"

    def test_float(self) -> None:
        assert substitute_named_with_literals("SELECT :a", {"a": 1.5}) == "SELECT 1.5"

    def test_float_nan_raises(self) -> None:
        with pytest.raises(ValueError, match="non-finite"):
            substitute_named_with_literals("SELECT :a", {"a": float("nan")})

    def test_float_inf_raises(self) -> None:
        with pytest.raises(ValueError, match="non-finite"):
            substitute_named_with_literals("SELECT :a", {"a": float("inf")})

    def test_float_neg_inf_raises(self) -> None:
        with pytest.raises(ValueError, match="non-finite"):
            substitute_named_with_literals("SELECT :a", {"a": float("-inf")})

    def test_bool_true_renders_as_one(self) -> None:
        # bool must NOT be rendered through the int branch.
        assert substitute_named_with_literals("SELECT :a", {"a": True}) == "SELECT 1"

    def test_bool_false_renders_as_zero(self) -> None:
        assert substitute_named_with_literals("SELECT :a", {"a": False}) == "SELECT 0"

    def test_str_simple(self) -> None:
        assert (
            substitute_named_with_literals("SELECT :a", {"a": "hello"})
            == "SELECT 'hello'"
        )

    def test_str_with_single_quote_escaped(self) -> None:
        assert (
            substitute_named_with_literals("SELECT :a", {"a": "O'Reilly"})
            == "SELECT 'O''Reilly'"
        )

    def test_none_renders_null(self) -> None:
        assert substitute_named_with_literals("SELECT :a", {"a": None}) == "SELECT NULL"

    def test_date(self) -> None:
        assert (
            substitute_named_with_literals("SELECT :a", {"a": dt.date(2024, 1, 2)})
            == "SELECT '2024-01-02'"
        )

    def test_datetime(self) -> None:
        value = dt.datetime(2024, 1, 2, 3, 4, 5)
        assert (
            substitute_named_with_literals("SELECT :a", {"a": value})
            == "SELECT '2024-01-02 03:04:05'"
        )

    def test_datetime_with_microseconds(self) -> None:
        value = dt.datetime(2024, 1, 2, 3, 4, 5, 678901)
        assert (
            substitute_named_with_literals("SELECT :a", {"a": value})
            == "SELECT '2024-01-02 03:04:05.678901'"
        )

    def test_decimal(self) -> None:
        assert (
            substitute_named_with_literals("SELECT :a", {"a": Decimal("3.14")})
            == "SELECT 3.14"
        )

    def test_bytes(self) -> None:
        # Exact hex rendering is dialect-dependent; assert the hex payload is
        # present rather than pinning sqlglot's literal form.
        result = substitute_named_with_literals("SELECT :a", {"a": b"\xde\xad\xbe\xef"})
        assert "deadbeef" in result.lower()

    def test_unsupported_type_raises_typeerror(self) -> None:
        with pytest.raises(TypeError, match="Unsupported SQL literal type"):
            substitute_named_with_literals("SELECT :a", {"a": set()})

    def test_placeholder_inside_string_not_substituted(self) -> None:
        result = substitute_named_with_literals("SELECT ':name' AS x", {})
        # The ``:name`` lives inside a string literal and is preserved as-is.
        assert "':name'" in result

    def test_placeholder_inside_line_comment_not_substituted(self) -> None:
        # ``:a`` is in a comment -> not a placeholder -> no KeyError, no literal.
        result = substitute_named_with_literals("SELECT 1 -- :a\nFROM t", {})
        assert "FROM" in result.upper()

    def test_placeholder_inside_block_comment_not_substituted(self) -> None:
        result = substitute_named_with_literals("SELECT 1 /* :a */ FROM t", {})
        assert "FROM" in result.upper()

    def test_repeated_placeholder_substituted_both_times(self) -> None:
        assert (
            substitute_named_with_literals("SELECT :a + :a", {"a": 5}) == "SELECT 5 + 5"
        )

    def test_missing_key_raises_keyerror(self) -> None:
        with pytest.raises(KeyError):
            substitute_named_with_literals("SELECT :a", {})

    def test_tsql_preserves_bracket_quoting_with_literal(self) -> None:
        # Under the tsql dialect, ``[id]`` bracket quoting is preserved and the
        # ``:id`` placeholder is substituted with its literal value.
        result = substitute_named_with_literals(
            "SELECT * FROM [orders] WHERE [id] = :id", {"id": 5}, "tsql"
        )
        assert "[id]" in result
        assert "[orders]" in result
        assert "= 5" in result
        assert "ARRAY(" not in result
        assert ":id" not in result


class TestReadOnlyViolation:
    """Tests for the read-only AST gate ``read_only_violation``."""

    def test_plain_select_is_read_only(self) -> None:
        assert read_only_violation("SELECT * FROM t", "sqlite") is None

    def test_with_select_is_read_only(self) -> None:
        assert (
            read_only_violation("WITH x AS (SELECT 1) SELECT * FROM x", "sqlite")
            is None
        )

    def test_values_is_read_only(self) -> None:
        assert read_only_violation("VALUES (1), (2)", "sqlite") is None

    def test_union_is_read_only(self) -> None:
        assert read_only_violation("SELECT 1 UNION SELECT 2", "sqlite") is None

    def test_insert_rejected(self) -> None:
        message = read_only_violation("INSERT INTO t VALUES (1)", "sqlite")
        assert message is not None
        assert "INSERT" in message

    def test_update_rejected(self) -> None:
        message = read_only_violation("UPDATE t SET a = 1", "sqlite")
        assert message is not None
        assert "UPDATE" in message

    def test_delete_rejected(self) -> None:
        message = read_only_violation("DELETE FROM t", "sqlite")
        assert message is not None
        assert "DELETE" in message

    def test_drop_rejected(self) -> None:
        message = read_only_violation("DROP TABLE t", "sqlite")
        assert message is not None
        assert "DROP" in message

    def test_create_rejected(self) -> None:
        message = read_only_violation("CREATE TABLE t (a int)", "sqlite")
        assert message is not None
        assert "CREATE" in message

    def test_alter_rejected(self) -> None:
        message = read_only_violation("ALTER TABLE t ADD COLUMN b int", "sqlite")
        assert message is not None
        assert "ALTER" in message

    def test_truncate_rejected(self) -> None:
        message = read_only_violation("TRUNCATE TABLE t", "tsql")
        assert message is not None
        assert "TRUNCATETABLE" in message

    def test_merge_rejected(self) -> None:
        message = read_only_violation(
            "MERGE INTO t USING s ON t.a = s.a WHEN MATCHED THEN DELETE", "tsql"
        )
        assert message is not None
        assert "MERGE" in message

    def test_select_into_rejected(self) -> None:
        message = read_only_violation("SELECT * INTO new_t FROM t", "tsql")
        assert message is not None
        assert "SELECT ... INTO" in message

    def test_data_modifying_cte_rejected(self) -> None:
        # The CTE wraps a DELETE; the root parses to a Delete node, which the
        # write-node walk catches anywhere in the tree.
        message = read_only_violation("WITH x AS (SELECT 1) DELETE FROM t", "tsql")
        assert message is not None
        assert "DELETE" in message

    def test_non_readonly_root_rejected_fail_closed(self) -> None:
        # ``PRAGMA`` parses cleanly to an exp.Pragma root which is NOT in the
        # read-only allow-list -- it must be rejected by the fail-closed gate.
        message = read_only_violation("PRAGMA table_info(t)", "sqlite")
        assert message is not None
        assert "SELECT/WITH/VALUES" in message

    def test_unparseable_sql_propagates_parse_error(self) -> None:
        with pytest.raises(sqlglot.errors.ParseError):
            read_only_violation("SELECT FROM WHERE )(", "sqlite")


class TestBuildCountQuery:
    """Tests for the COUNT-wrap helper ``build_count_query``."""

    def test_basic_wrapper_shape(self) -> None:
        result = build_count_query("SELECT * FROM customers", "sqlite")
        assert "COUNT(*)" in result
        assert "row_count" in result
        assert "count_sub" in result

    def test_wrapper_is_valid_read_only(self) -> None:
        # The wrapper itself must still parse to a read-only construct.
        result = build_count_query("SELECT * FROM customers", "sqlite")
        assert read_only_violation(result, "sqlite") is None

    def test_placeholder_preserved_sqlite(self) -> None:
        result = build_count_query("SELECT * FROM t WHERE id = :id", "sqlite")
        assert ":id" in result
        # The preserved ``:id`` is still a bindable placeholder node.
        reparsed = sqlglot.parse_one(result, read="sqlite")
        names = {ph.name for ph in reparsed.find_all(exp.Placeholder)}
        assert "id" in names

    def test_placeholder_preserved_tsql(self) -> None:
        result = build_count_query("SELECT * FROM t WHERE id = :id", "tsql")
        # Rendered T-SQL stays parseable under the tsql dialect.
        reparsed = sqlglot.parse_one(result, read="tsql")
        names = {ph.name for ph in reparsed.find_all(exp.Placeholder)}
        assert "id" in names

    def test_wraps_union_query(self) -> None:
        result = build_count_query("SELECT 1 UNION SELECT 2", "sqlite")
        assert "COUNT(*)" in result
        assert "count_sub" in result

    def test_wraps_values_query(self) -> None:
        # ``VALUES`` is an accepted read-only root but is not an exp.Query, so
        # the wrapper must build the derived table without ``.subquery``.
        result = build_count_query("VALUES (1), (2)", "sqlite")
        assert "COUNT(*)" in result
        assert "count_sub" in result

    def test_drops_order_by_tsql(self) -> None:
        # T-SQL rejects ORDER BY inside a derived table (error 1033) unless
        # accompanied by TOP/OFFSET/FOR XML. COUNT(*) is order-independent, so
        # the statement-level ORDER BY must be dropped before wrapping.
        sql = (
            "SELECT TABLE_NAME AS name FROM INFORMATION_SCHEMA.TABLES "
            "WHERE TABLE_SCHEMA = :schema ORDER BY name"
        )
        result = build_count_query(sql, "tsql")
        assert "ORDER BY" not in result.upper()
        # The ``:schema`` placeholder survives as a bindable node.
        reparsed = sqlglot.parse_one(result, read="tsql")
        names = {ph.name for ph in reparsed.find_all(exp.Placeholder)}
        assert "schema" in names

    def test_drops_order_by_sqlite(self) -> None:
        sql = (
            "SELECT TABLE_NAME AS name FROM INFORMATION_SCHEMA.TABLES "
            "WHERE TABLE_SCHEMA = :schema ORDER BY name"
        )
        result = build_count_query(sql, "sqlite")
        assert "ORDER BY" not in result.upper()
        reparsed = sqlglot.parse_one(result, read="sqlite")
        names = {ph.name for ph in reparsed.find_all(exp.Placeholder)}
        assert "schema" in names

    def test_no_order_by_unchanged_wrapper(self) -> None:
        # A query without ORDER BY is wrapped exactly as before (regression).
        result = build_count_query("SELECT * FROM customers", "tsql")
        assert "ORDER BY" not in result.upper()
        assert "COUNT(*)" in result
        assert "count_sub" in result

    def test_qualified_names_preserved(self) -> None:
        # Three-part qualified names survive the ORDER BY stripping + wrapping.
        result = build_count_query("SELECT * FROM sales.dbo.orders ORDER BY id", "tsql")
        assert "ORDER BY" not in result.upper()
        assert "sales.dbo.orders" in result


class TestHasLeadingCte:
    """Tests for the shared leading-CTE gate ``has_leading_cte``."""

    @pytest.mark.parametrize("dialect", ["sqlite", "tsql"])
    def test_leading_cte_detected(self, dialect: str) -> None:
        sql = "WITH c AS (SELECT 1 AS a) SELECT a FROM c"
        assert has_leading_cte(sql, dialect) is True

    @pytest.mark.parametrize("dialect", ["sqlite", "tsql"])
    def test_plain_select_is_not_a_cte(self, dialect: str) -> None:
        assert has_leading_cte("SELECT * FROM t", dialect) is False

    def test_tsql_nolock_hint_not_false_positived(self) -> None:
        # ``WITH (NOLOCK)`` is a table hint: sqlglot models it on the table
        # node, not the statement-level CTE arg.
        assert has_leading_cte("SELECT * FROM t WITH (NOLOCK)", "tsql") is False

    def test_nested_cte_in_subquery_is_not_statement_level(self) -> None:
        # The gate is statement-level only: a CTE buried inside a derived
        # table leaves the root statement's ``with`` arg unset.
        sql = "SELECT * FROM (WITH c AS (SELECT 1 AS a) SELECT a FROM c) AS x"
        assert has_leading_cte(sql, "sqlite") is False


class TestLeadingCteRejection:
    """Tests for the shared rejection message ``LEADING_CTE_REJECTION``."""

    def test_message_names_the_cause(self) -> None:
        assert isinstance(LEADING_CTE_REJECTION, str)
        assert LEADING_CTE_REJECTION.strip() != ""
        assert "WITH" in LEADING_CTE_REJECTION
        assert "SQL Server" in LEADING_CTE_REJECTION
