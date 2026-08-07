"""Tests for speaker-turn audio segmentation."""

from eventforge.services.preprocessing.asr import Utterance
from eventforge.services.preprocessing.audio_segments import build_speaker_turns


def test_build_speaker_turns_merges_same_speaker() -> None:
    utterances = [
        Utterance("Hello.", 0, 4_000, -0.3),
        Utterance("How can I help?", 4_000, 8_000, -0.4),
        Utterance("I need help with billing.", 8_000, 12_000, -0.5),
    ]
    roles = ["agent", "agent", "customer"]

    pieces = build_speaker_turns(
        utterances,
        roles,
        asr_model="mock/test",
    )

    assert len(pieces) == 2
    assert pieces[0].metadata_json["speaker"] == "agent"
    assert pieces[0].metadata_json["kind"] == "audio_turn"
    assert pieces[0].start_ms == 0
    assert pieces[0].end_ms == 8_000
    assert "How can I help?" in pieces[0].content
    assert pieces[1].metadata_json["speaker"] == "customer"
    assert pieces[1].start_ms == 8_000
    assert pieces[1].end_ms == 12_000


def test_build_speaker_turns_splits_on_role_change() -> None:
    utterances = [
        Utterance("Agent line.", 0, 5_000, -0.2),
        Utterance("Customer line.", 5_000, 10_000, -0.4),
        Utterance("Agent reply.", 10_000, 15_000, -0.3),
    ]
    roles = ["agent", "customer", "agent"]

    pieces = build_speaker_turns(
        utterances,
        roles,
        asr_model="mock/test",
    )

    assert len(pieces) == 3
    assert [piece.metadata_json["speaker"] for piece in pieces] == [
        "agent",
        "customer",
        "agent",
    ]


def test_build_speaker_turns_splits_long_turn_at_utterance_boundary() -> None:
    utterances = [
        Utterance("Part one.", 0, 35_000, -0.2),
        Utterance("Part two.", 35_000, 70_000, -0.3),
    ]
    roles = ["agent", "agent"]

    pieces = build_speaker_turns(
        utterances,
        roles,
        asr_model="mock/test",
        max_turn_ms=60_000,
    )

    assert len(pieces) == 2
    assert pieces[0].metadata_json["speaker"] == "agent"
    assert pieces[0].end_ms - pieces[0].start_ms <= 60_000
    assert pieces[1].metadata_json["speaker"] == "agent"


def test_build_speaker_turns_returns_empty_for_blank_transcript() -> None:
    assert build_speaker_turns([], [], asr_model="mock/test") == []


def test_build_speaker_turns_skips_blank_utterance_and_keeps_roles() -> None:
    utterances = [
        Utterance("   ", 0, 2_000, -0.2),
        Utterance("Customer line.", 2_000, 6_000, -0.3),
    ]
    roles = ["agent", "customer"]

    pieces = build_speaker_turns(
        utterances,
        roles,
        asr_model="mock/test",
    )

    assert len(pieces) == 1
    assert pieces[0].metadata_json["speaker"] == "customer"
    assert pieces[0].content == "Customer line."


def test_build_speaker_turns_splits_single_oversized_utterance() -> None:
    words = " ".join(f"word{i}" for i in range(20))
    utterances = [Utterance(words, 0, 90_000, -0.2)]
    roles = ["agent"]

    pieces = build_speaker_turns(
        utterances,
        roles,
        asr_model="mock/test",
        max_turn_ms=60_000,
    )

    assert len(pieces) >= 2
    assert all(piece.metadata_json["speaker"] == "agent" for piece in pieces)
    assert all(piece.end_ms - piece.start_ms <= 60_000 for piece in pieces)
