"""Tests for ASR utterance windowing."""

from eventforge.services.preprocessing.asr import Utterance
from eventforge.services.preprocessing.audio_segments import window_utterances


def test_window_utterances_merges_short_spans() -> None:
    utterances = [
        Utterance("Hello.", 0, 4_000, -0.3),
        Utterance("I need help with billing.", 4_000, 12_000, -0.5),
    ]

    pieces = window_utterances(
        utterances,
        asr_model="mock/test",
        min_window_ms=15_000,
        max_window_ms=45_000,
    )

    assert len(pieces) == 1
    assert pieces[0].segment_index == 0
    assert pieces[0].start_ms == 0
    assert pieces[0].end_ms == 12_000
    assert "billing" in pieces[0].content
    assert pieces[0].metadata_json["kind"] == "audio_utterance"
    assert pieces[0].metadata_json["asr_model"] == "mock/test"
    assert pieces[0].metadata_json["asr_avg_logprob"] == -0.4


def test_window_utterances_splits_when_over_max_window() -> None:
    utterances = [
        Utterance("First part.", 0, 20_000, -0.2),
        Utterance("Second part.", 20_000, 50_000, -0.4),
    ]

    pieces = window_utterances(
        utterances,
        asr_model="mock/test",
        min_window_ms=15_000,
        max_window_ms=45_000,
    )

    assert len(pieces) == 2
    assert pieces[0].end_ms - pieces[0].start_ms <= 45_000
    assert pieces[1].start_ms == 20_000


def test_window_utterances_returns_empty_for_blank_transcript() -> None:
    assert window_utterances([], asr_model="mock/test") == []
