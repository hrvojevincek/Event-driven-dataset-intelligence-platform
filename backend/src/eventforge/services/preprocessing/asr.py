"""Automatic speech recognition providers for audio preprocessing."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from eventforge.core.config import Settings
from eventforge.core.otel import agent_span

_local_asr_lock = threading.Lock()
_local_asr_cache: dict[tuple[str, str], FasterWhisperASR] = {}


@dataclass(frozen=True)
class Utterance:
    """One ASR transcript span with millisecond bounds."""

    text: str
    start_ms: int
    end_ms: int
    avg_logprob: float | None = None


class ASRProvider(Protocol):
    """Transcribe a local audio file into timed utterances."""

    @property
    def model_name(self) -> str:
        """Provider-specific model identifier for provenance."""
        ...

    def transcribe(self, path: Path) -> list[Utterance]:
        """Return non-empty utterances ordered by start time."""
        ...


class FasterWhisperASR:
    """Local transcription via faster-whisper (CPU-friendly demo default)."""

    def __init__(self, *, model_size: str = "small", device: str = "cpu") -> None:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            msg = (
                "faster-whisper is not installed. "
                "Install with: uv sync --extra asr"
            )
            raise RuntimeError(msg) from exc

        self._model_size = model_size
        self._device = device
        with agent_span("asr", "load") as span:
            span.set_attribute("asr.model_size", model_size)
            span.set_attribute("asr.device", device)
            span.set_attribute("asr.compute_type", "int8")
            span.set_attribute("asr.cache_hit", False)
            self._model = WhisperModel(model_size, device=device, compute_type="int8")

    @property
    def model_name(self) -> str:
        return f"faster-whisper/{self._model_size}"

    def transcribe(self, path: Path) -> list[Utterance]:
        with agent_span("asr", "transcribe") as span:
            span.set_attribute("asr.model", self.model_name)
            span.set_attribute("asr.beam_size", 1)
            span.set_attribute("asr.vad_filter", True)
            span.set_attribute("asr.path", path.name)
            segments, _info = self._model.transcribe(
                str(path),
                vad_filter=True,
                beam_size=1,
            )
            utterances: list[Utterance] = []
            for segment in segments:
                text = segment.text.strip()
                if not text:
                    continue
                utterances.append(
                    Utterance(
                        text=text,
                        start_ms=int(segment.start * 1000),
                        end_ms=int(segment.end * 1000),
                        avg_logprob=getattr(segment, "avg_logprob", None),
                    )
                )
            span.set_attribute("asr.utterance_count", len(utterances))
            return utterances


class OpenAIWhisperASR:
    """Cloud transcription via OpenAI Whisper API."""

    def __init__(self, settings: Settings, *, model: str = "whisper-1") -> None:
        if not settings.openai_api_key:
            msg = "OPENAI_API_KEY is required when ASR_PROVIDER=openai"
            raise RuntimeError(msg)
        from openai import OpenAI

        self._client = OpenAI(api_key=settings.openai_api_key)
        self._model = model

    @property
    def model_name(self) -> str:
        return f"openai/{self._model}"

    def transcribe(self, path: Path) -> list[Utterance]:
        with agent_span("asr", "transcribe") as span:
            span.set_attribute("asr.model", self.model_name)
            span.set_attribute("asr.path", path.name)
            with path.open("rb") as audio_file:
                response = self._client.audio.transcriptions.create(
                    model=self._model,
                    file=audio_file,
                    response_format="verbose_json",
                    timestamp_granularities=["segment"],
                )

            utterances: list[Utterance] = []
            for segment in response.segments or []:
                text = segment.text.strip()
                if not text:
                    continue
                utterances.append(
                    Utterance(
                        text=text,
                        start_ms=int(segment.start * 1000),
                        end_ms=int(segment.end * 1000),
                    )
                )
            span.set_attribute("asr.utterance_count", len(utterances))
            return utterances


def get_asr_provider(settings: Settings) -> ASRProvider:
    """Return the configured ASR provider (local Whisper is process-cached)."""
    if settings.asr_provider == "openai":
        return OpenAIWhisperASR(settings, model=settings.asr_openai_model)

    cache_key = (settings.asr_local_model, settings.asr_device)
    with _local_asr_lock:
        cached = _local_asr_cache.get(cache_key)
        if cached is not None:
            with agent_span("asr", "load") as span:
                span.set_attribute("asr.model_size", cache_key[0])
                span.set_attribute("asr.device", cache_key[1])
                span.set_attribute("asr.cache_hit", True)
            return cached

        provider = FasterWhisperASR(
            model_size=settings.asr_local_model,
            device=settings.asr_device,
        )
        _local_asr_cache[cache_key] = provider
        return provider


def reset_local_asr_cache() -> None:
    """Clear the process-local faster-whisper cache (tests / worker restarts)."""
    with _local_asr_lock:
        _local_asr_cache.clear()
