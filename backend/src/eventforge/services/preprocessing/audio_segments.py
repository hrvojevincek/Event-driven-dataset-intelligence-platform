"""Merge ASR utterances into speaker-turn audio segments."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from eventforge.services.preprocessing.asr import Utterance

SpeakerRole = Literal["agent", "customer"]
DEFAULT_MAX_TURN_MS = 60_000


@dataclass(frozen=True)
class AudioSegmentPiece:
    """Preprocessed audio slice ready to persist as a Segment row."""

    content: str
    start_ms: int
    end_ms: int
    segment_index: int
    metadata_json: dict[str, Any]


def build_speaker_turns(
    utterances: list[Utterance],
    roles: list[SpeakerRole],
    *,
    asr_model: str,
    max_turn_ms: int = DEFAULT_MAX_TURN_MS,
) -> list[AudioSegmentPiece]:
    """Merge consecutive same-speaker utterances into annotation turns."""
    if max_turn_ms <= 0:
        msg = "invalid max turn duration"
        raise ValueError(msg)
    if len(roles) != len(utterances):
        msg = "role count must match utterance count"
        raise ValueError(msg)

    paired = _paired_utterances(utterances, roles)
    if not paired:
        return []

    turns = _group_by_speaker(paired)
    split_turns = _split_long_turns(turns, max_turn_ms=max_turn_ms)

    pieces: list[AudioSegmentPiece] = []
    for index, (window, speaker, start_ms, end_ms) in enumerate(split_turns):
        content = " ".join(part.text for part in window).strip()
        if not content:
            continue
        avg_logprob = _average_logprob(window)
        metadata: dict[str, Any] = {
            "kind": "audio_turn",
            "speaker": speaker,
            "asr_model": asr_model,
            "utterance_count": len(window),
        }
        if avg_logprob is not None:
            metadata["asr_avg_logprob"] = round(avg_logprob, 4)
        pieces.append(
            AudioSegmentPiece(
                content=content,
                start_ms=start_ms,
                end_ms=end_ms,
                segment_index=index,
                metadata_json=metadata,
            )
        )
    return pieces


def _paired_utterances(
    utterances: list[Utterance],
    roles: list[SpeakerRole],
) -> list[tuple[Utterance, SpeakerRole]]:
    paired: list[tuple[Utterance, SpeakerRole]] = []
    for utterance, role in zip(utterances, roles, strict=True):
        text = utterance.text.strip()
        if not text:
            continue
        paired.append(
            (
                Utterance(
                    text=text,
                    start_ms=utterance.start_ms,
                    end_ms=utterance.end_ms,
                    avg_logprob=utterance.avg_logprob,
                ),
                role,
            )
        )
    return paired


def _group_by_speaker(
    paired: list[tuple[Utterance, SpeakerRole]],
) -> list[tuple[list[Utterance], SpeakerRole, int, int]]:
    turns: list[tuple[list[Utterance], SpeakerRole, int, int]] = []
    buffer: list[Utterance] = []
    buffer_role: SpeakerRole | None = None
    buffer_start = 0
    buffer_end = 0

    for utterance, role in paired:
        if not buffer:
            buffer = [utterance]
            buffer_role = role
            buffer_start = utterance.start_ms
            buffer_end = utterance.end_ms
            continue

        if role == buffer_role:
            buffer.append(utterance)
            buffer_end = utterance.end_ms
            continue

        turns.append((buffer, buffer_role, buffer_start, buffer_end))
        buffer = [utterance]
        buffer_role = role
        buffer_start = utterance.start_ms
        buffer_end = utterance.end_ms

    if buffer and buffer_role is not None:
        turns.append((buffer, buffer_role, buffer_start, buffer_end))
    return turns


def _split_long_turns(
    turns: list[tuple[list[Utterance], SpeakerRole, int, int]],
    *,
    max_turn_ms: int,
) -> list[tuple[list[Utterance], SpeakerRole, int, int]]:
    split: list[tuple[list[Utterance], SpeakerRole, int, int]] = []
    for window, speaker, start_ms, end_ms in turns:
        if end_ms - start_ms <= max_turn_ms:
            split.append((window, speaker, start_ms, end_ms))
            continue

        expanded = _expand_oversized_utterances(window, max_turn_ms=max_turn_ms)
        chunk: list[Utterance] = []
        chunk_start = expanded[0].start_ms
        chunk_end = expanded[0].end_ms
        for utterance in expanded:
            candidate_end = utterance.end_ms
            if chunk and candidate_end - chunk_start > max_turn_ms:
                split.append((chunk, speaker, chunk_start, chunk_end))
                chunk = [utterance]
                chunk_start = utterance.start_ms
                chunk_end = utterance.end_ms
                continue
            if not chunk:
                chunk_start = utterance.start_ms
            chunk.append(utterance)
            chunk_end = utterance.end_ms
        if chunk:
            split.append((chunk, speaker, chunk_start, chunk_end))
    return split


def _expand_oversized_utterances(
    utterances: list[Utterance],
    *,
    max_turn_ms: int,
) -> list[Utterance]:
    expanded: list[Utterance] = []
    for utterance in utterances:
        duration = utterance.end_ms - utterance.start_ms
        if duration <= max_turn_ms:
            expanded.append(utterance)
            continue
        words = utterance.text.split()
        if len(words) < 2:
            expanded.append(utterance)
            continue
        chunk_count = max(2, (duration + max_turn_ms - 1) // max_turn_ms)
        words_per_chunk = max(1, len(words) // chunk_count)
        for chunk_index in range(chunk_count):
            start_word = chunk_index * words_per_chunk
            if chunk_index == chunk_count - 1:
                end_word = len(words)
            else:
                end_word = (chunk_index + 1) * words_per_chunk
            chunk_words = words[start_word:end_word]
            if not chunk_words:
                continue
            span_start = utterance.start_ms + int(duration * (start_word / len(words)))
            span_end = utterance.start_ms + int(duration * (end_word / len(words)))
            expanded.append(
                Utterance(
                    text=" ".join(chunk_words),
                    start_ms=span_start,
                    end_ms=max(span_end, span_start + 1),
                    avg_logprob=utterance.avg_logprob,
                )
            )
    return expanded


def _average_logprob(window: list[Utterance]) -> float | None:
    """Mean utterance avg_logprob across the turn (log-space, typically ≤ 0)."""
    values = [item.avg_logprob for item in window if item.avg_logprob is not None]
    if not values:
        return None
    return sum(values) / len(values)
