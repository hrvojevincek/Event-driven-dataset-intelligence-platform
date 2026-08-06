"""Unit tests for intake upload validation."""

import math
import struct
import wave
from io import BytesIO

import pytest

from eventforge.services.intake.templates import (
    allowed_extensions_for_template,
    domain_for_template,
)
from eventforge.services.intake.validation import (
    MAX_AUDIO_DURATION_SECONDS,
    validate_upload,
)


def _make_wav(*, seconds: float, sample_rate: int = 16000) -> bytes:
    buffer = BytesIO()
    frames = int(sample_rate * seconds)
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        for i in range(frames):
            sample = int(8000 * math.sin(2 * math.pi * 440 * (i / sample_rate)))
            wav.writeframes(struct.pack("<h", sample))
    return buffer.getvalue()


def test_validate_upload_accepts_txt_for_support_call_template() -> None:
    result = validate_upload(
        "call_001.txt",
        b"Customer: I need help.\n",
        max_bytes=1024,
        schema_template="support_call",
    )
    assert result.mime_type == "text/plain"
    assert result.filename == "call_001.txt"


def test_validate_upload_accepts_wav_for_audio_template() -> None:
    content = _make_wav(seconds=2.0)
    result = validate_upload(
        "call_001.wav",
        content,
        max_bytes=len(content) + 1,
        schema_template="support_call_audio",
    )
    assert result.mime_type == "audio/wav"
    assert result.provenance["duration_seconds"] == pytest.approx(2.0, abs=0.01)


def test_validate_upload_rejects_wav_for_text_support_call_template() -> None:
    content = _make_wav(seconds=1.0)
    with pytest.raises(ValueError, match="Unsupported file type"):
        validate_upload(
            "call_001.wav",
            content,
            max_bytes=len(content) + 1,
            schema_template="support_call",
        )


def test_validate_upload_rejects_txt_for_audio_template() -> None:
    with pytest.raises(ValueError, match="Unsupported file type"):
        validate_upload(
            "call_001.txt",
            b"hello",
            max_bytes=1024,
            schema_template="support_call_audio",
        )


def test_validate_upload_rejects_audio_over_duration_limit() -> None:
    content = _make_wav(seconds=MAX_AUDIO_DURATION_SECONDS + 1)
    with pytest.raises(ValueError, match="minute audio limit"):
        validate_upload(
            "long_call.wav",
            content,
            max_bytes=len(content) + 1,
            schema_template="support_call_audio",
        )


def test_validate_upload_rejects_invalid_wav_bytes() -> None:
    with pytest.raises(ValueError, match="not a valid WAV"):
        validate_upload(
            "bad.wav",
            b"not-a-wav",
            max_bytes=1024,
            schema_template="support_call_audio",
        )


def test_domain_for_template_maps_audio_and_support_calls() -> None:
    assert domain_for_template("support_call_audio") == "audio"
    assert domain_for_template("support_call") == "support_calls"
    assert domain_for_template("document_classification") == "documents"
    assert domain_for_template(None) == "documents"


def test_allowed_extensions_for_template() -> None:
    assert ".wav" in allowed_extensions_for_template("support_call_audio")
    assert ".wav" not in allowed_extensions_for_template("support_call")
    assert ".pdf" in allowed_extensions_for_template("document_classification")
