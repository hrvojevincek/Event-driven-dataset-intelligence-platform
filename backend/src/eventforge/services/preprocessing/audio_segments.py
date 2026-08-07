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

    normalized = _normalize_utterances(utterances)
    if not normalized:
        return []

    turns = _group_by_speaker(normalized, roles)
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


def _normalize_utterances(utterances: list[Utterance]) -> list[Utterance]:
    normalized: list[Utterance] = []
    for utterance in utterances:
        text = utterance.text.strip()
        if not text:
            continue
        normalized.append(
            Utterance(
                text=text,
                start_ms=utterance.start_ms,
                end_ms=utterance.end_ms,
                avg_logprob=utterance.avg_logprob,
            )
        )
    return normalized


def _group_by_speaker(
    utterances: list[Utterance],
    roles: list[SpeakerRole],
) -> list[tuple[list[Utterance], SpeakerRole, int, int]]:
    turns: list[tuple[list[Utterance], SpeakerRole, int, int]] = []
    buffer: list[Utterance] = []
    buffer_role: SpeakerRole | None = None
    buffer_start = 0
    buffer_end = 0

    for utterance, role in zip(utterances, roles, strict=True):
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

        chunk: list[Utterance] = []
        chunk_start = window[0].start_ms
        chunk_end = window[0].end_ms
        for utterance in window:
            candidate_end = utterance.end_ms
            if chunk and candidate_end - chunk_start > max_turn_ms:
                split.append((chunk, speaker, chunk_start, chunk_end))
                chunk = [utterance]
                chunk_start = utterance.start_ms
                chunk_end = utterance.end_ms
                continue
            chunk.append(utterance)
            chunk_end = utterance.end_ms
        if chunk:
            split.append((chunk, speaker, chunk_start, chunk_end))
    return split


def _average_logprob(window: list[Utterance]) -> float | None:
    """Mean utterance avg_logprob across the turn (log-space, typically ≤ 0)."""
    values = [item.avg_logprob for item in window if item.avg_logprob is not None]
    if not values:
        return None
    return sum(values) / len(values)
