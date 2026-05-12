"""Unit tests for the shared identifier helper module."""

from __future__ import annotations

from mcp_tools_sql.identifiers import IDENTIFIER_PATTERN, identifier_error


class TestIdentifierPattern:
    """Whitelist regex accepts conformant names and rejects everything else."""

    def test_valid_identifier_matches(self) -> None:
        assert IDENTIFIER_PATTERN.match("good_name_1") is not None

    def test_space_rejected(self) -> None:
        assert IDENTIFIER_PATTERN.match("bad name") is None

    def test_leading_digit_rejected(self) -> None:
        assert IDENTIFIER_PATTERN.match("1leading_digit") is None

    def test_dash_rejected(self) -> None:
        assert IDENTIFIER_PATTERN.match("with-dash") is None


class TestIdentifierError:
    """``identifier_error`` mentions the offender, the owner and the rule."""

    def test_mentions_value_and_update_name(self) -> None:
        msg = identifier_error("bad name", "set_status")
        assert "bad name" in msg
        assert "set_status" in msg

    def test_mentions_whitelist_intent(self) -> None:
        msg = identifier_error("bad name", "set_status")
        assert "intentionally restricted" in msg
        assert IDENTIFIER_PATTERN.pattern in msg
