"""Merge ASR utterances into annotation-sized audio segment windows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from eventforge.services.preprocessing.asr import Utterance

DEFAULT_MIN_WINDOW_MS = 15_000
DEFAULT_MAX_WINDOW_MS = 45_000


@dataclass(frozen=True)
class AudioSegmentPiece:
    """Preprocessed audio slice ready to persist as a Segment row."""

    content: str
    start_ms: int
    end_ms: int
    segment_index: int
    metadata_json: dict[str, Any]


def window_utterances(
    utterances: list[Utterance],
    *,
    asr_model: str,
    min_window_ms: int = DEFAULT_MIN_WINDOW_MS,
    max_window_ms: int = DEFAULT_MAX_WINDOW_MS,
) -> list[AudioSegmentPiece]:
    """Merge or split utterances into stable ~15–45s transcript windows."""
    if min_window_ms <= 0 or max_window_ms <= 0 or min_window_ms > max_window_ms:
        msg = "invalid audio window bounds"
        raise ValueError(msg)

    expanded = _expand_long_utterances(utterances, max_window_ms=max_window_ms)
    if not expanded:
        return []

    windows: list[tuple[list[Utterance], int, int]] = []
    buffer: list[Utterance] = []
    buffer_start = expanded[0].start_ms
    buffer_end = expanded[0].end_ms

    for utterance in expanded:
        if not buffer:
            buffer = [utterance]
            buffer_start = utterance.start_ms
            buffer_end = utterance.end_ms
            continue

        candidate_end = utterance.end_ms
        candidate_duration = candidate_end - buffer_start
        if candidate_duration <= max_window_ms:
            buffer.append(utterance)
            buffer_end = candidate_end
            continue

        windows.append((buffer, buffer_start, buffer_end))
        buffer = [utterance]
        buffer_start = utterance.start_ms
        buffer_end = utterance.end_ms

    if buffer:
        windows.append((buffer, buffer_start, buffer_end))

    merged = _merge_trailing_short_window(
        windows,
        min_window_ms=min_window_ms,
        max_window_ms=max_window_ms,
    )

    pieces: list[AudioSegmentPiece] = []
    for index, (window, start_ms, end_ms) in enumerate(merged):
        content = " ".join(part.text for part in window).strip()
        if not content:
            continue
        avg_logprob = _average_logprob(window)
        metadata: dict[str, Any] = {
            "kind": "audio_utterance",
            "asr_model": asr_model,
            "utterance_count": len(window),
        }
        if avg_logprob is not None:
            # faster-whisper avg_logprob is log-space, not 0–1 confidence
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


def _expand_long_utterances(
    utterances: list[Utterance],
    *,
    max_window_ms: int,
) -> list[Utterance]:
    expanded: list[Utterance] = []
    for utterance in utterances:
        text = utterance.text.strip()
        if not text:
            continue
        duration = utterance.end_ms - utterance.start_ms
        if duration <= max_window_ms:
            expanded.append(
                Utterance(
                    text=text,
                    start_ms=utterance.start_ms,
                    end_ms=utterance.end_ms,
                    avg_logprob=utterance.avg_logprob,
                )
            )
            continue
        words = text.split()
        if len(words) < 2:
            expanded.append(
                Utterance(
                    text=text,
                    start_ms=utterance.start_ms,
                    end_ms=utterance.end_ms,
                    avg_logprob=utterance.avg_logprob,
                )
            )
            continue
        chunk_count = max(2, (duration + max_window_ms - 1) // max_window_ms)
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


def _merge_trailing_short_window(
    windows: list[tuple[list[Utterance], int, int]],
    *,
    min_window_ms: int,
    max_window_ms: int,
) -> list[tuple[list[Utterance], int, int]]:
    if len(windows) < 2:
        return windows

    merged = list(windows)
    last_window, last_start, last_end = merged[-1]
    if (last_end - last_start) >= min_window_ms:
        return merged

    prev_window, prev_start, prev_end = merged[-2]
    combined_duration = last_end - prev_start
    if combined_duration <= max_window_ms:
        merged[-2] = (prev_window + last_window, prev_start, last_end)
        merged.pop()
    return merged


def _average_logprob(window: list[Utterance]) -> float | None:
    """Mean utterance avg_logprob across the window (log-space, typically ≤ 0)."""
    values = [item.avg_logprob for item in window if item.avg_logprob is not None]
    if not values:
        return None
    return sum(values) / len(values)
