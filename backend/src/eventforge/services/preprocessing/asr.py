"""Automatic speech recognition providers for audio preprocessing."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from eventforge.core.config import Settings


@dataclass(frozen=True)
class Utterance:
    """One ASR transcript span with millisecond bounds."""

    text: str
    start_ms: int
    end_ms: int
    confidence: float | None = None


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
        self._model = WhisperModel(model_size, device=device, compute_type="int8")

    @property
    def model_name(self) -> str:
        return f"faster-whisper/{self._model_size}"

    def transcribe(self, path: Path) -> list[Utterance]:
        segments, _info = self._model.transcribe(str(path), vad_filter=True)
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
                    confidence=getattr(segment, "avg_logprob", None),
                )
            )
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
        return utterances


def get_asr_provider(settings: Settings) -> ASRProvider:
    """Build the configured ASR provider."""
    if settings.asr_provider == "openai":
        return OpenAIWhisperASR(settings, model=settings.asr_openai_model)
    return FasterWhisperASR(model_size=settings.asr_local_model, device=settings.asr_device)
