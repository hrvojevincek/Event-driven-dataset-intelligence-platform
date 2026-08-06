"""Validate uploaded files before persisting assets."""

import hashlib
import mimetypes
import wave
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from eventforge.services.intake.audio import probe_wav_duration_seconds
from eventforge.services.intake.templates import allowed_extensions_for_template

MAX_AUDIO_DURATION_SECONDS = 5 * 60


@dataclass(frozen=True)
class ValidatedUpload:
    """Normalized upload metadata produced during intake validation."""

    filename: str
    mime_type: str
    byte_size: int
    content_hash: str
    provenance: dict[str, Any]


def detect_mime_type(filename: str, content: bytes) -> str:
    """Guess MIME type from filename with a small binary sniff fallback."""
    guessed, _ = mimetypes.guess_type(filename)
    if guessed:
        return guessed
    if content.startswith(b"%PDF"):
        return "application/pdf"
    if content[:4] == b"RIFF" and content[8:12] == b"WAVE":
        return "audio/wav"
    return "text/plain"


def validate_upload(
    filename: str,
    content: bytes,
    *,
    max_bytes: int,
    schema_template: str | None = None,
    max_audio_duration_seconds: int = MAX_AUDIO_DURATION_SECONDS,
) -> ValidatedUpload:
    """Ensure extension, size, MIME type, and audio duration are acceptable."""
    extension = Path(filename).suffix.lower()
    allowed_extensions = allowed_extensions_for_template(schema_template)
    if extension not in allowed_extensions:
        allowed = ", ".join(sorted(allowed_extensions))
        msg = f"Unsupported file type '{extension or '(none)'}'. Allowed: {allowed}"
        raise ValueError(msg)
    if not content:
        msg = f"File '{filename}' is empty"
        raise ValueError(msg)
    if len(content) > max_bytes:
        msg = f"File '{filename}' exceeds max size of {max_bytes} bytes"
        raise ValueError(msg)

    mime_type = detect_mime_type(filename, content)
    if extension == ".pdf" and mime_type not in {"application/pdf", "application/octet-stream"}:
        msg = f"File '{filename}' is not a valid PDF"
        raise ValueError(msg)
    if extension == ".wav":
        if mime_type not in {"audio/wav", "audio/x-wav", "audio/wave", "application/octet-stream"}:
            msg = f"File '{filename}' is not a valid WAV"
            raise ValueError(msg)
        try:
            duration_seconds = probe_wav_duration_seconds(content)
        except (wave.Error, ValueError) as exc:
            msg = f"File '{filename}' is not a valid WAV"
            raise ValueError(msg) from exc
        if duration_seconds > max_audio_duration_seconds:
            limit_minutes = max_audio_duration_seconds // 60
            msg = (
                f"File '{filename}' exceeds the {limit_minutes}-minute audio limit "
                f"({duration_seconds:.1f}s)"
            )
            raise ValueError(msg)

    content_hash = hashlib.sha256(content).hexdigest()
    provenance = {
        "original_filename": Path(filename).name,
        "content_hash_sha256": content_hash,
        "uploaded_at": datetime.now(tz=UTC).isoformat(),
        "mime_type": mime_type,
    }
    if extension == ".wav":
        provenance["duration_seconds"] = round(duration_seconds, 3)

    return ValidatedUpload(
        filename=Path(filename).name,
        mime_type=mime_type if extension != ".wav" else "audio/wav",
        byte_size=len(content),
        content_hash=content_hash,
        provenance=provenance,
    )
