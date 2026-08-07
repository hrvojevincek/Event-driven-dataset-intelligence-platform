"""Tests for LLM speaker role classification parsing."""

import pytest

from eventforge.services.preprocessing.speaker_roles import _parse_roles


def test_parse_roles_accepts_valid_response() -> None:
    content = '{"roles": {"0": "agent", "1": "customer"}}'
    assert _parse_roles(content, 2) == ["agent", "customer"]


def test_parse_roles_strips_markdown_fences() -> None:
    content = '```json\n{"roles": {"0": "customer"}}\n```'
    assert _parse_roles(content, 1) == ["customer"]


def test_parse_roles_rejects_invalid_json() -> None:
    with pytest.raises(ValueError, match="valid JSON"):
        _parse_roles("not json", 1)


def test_parse_roles_rejects_missing_role() -> None:
    content = '{"roles": {"0": "agent"}}'
    with pytest.raises(ValueError, match="invalid role for utterance index 1"):
        _parse_roles(content, 2)


def test_parse_roles_rejects_unknown_role() -> None:
    content = '{"roles": {"0": "supervisor"}}'
    with pytest.raises(ValueError, match="invalid role for utterance index 0"):
        _parse_roles(content, 1)
