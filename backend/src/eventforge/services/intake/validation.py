"""Validate uploaded files before persisting assets."""

import hashlib
import mimetypes
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ALLOWED_EXTENSIONS = {".txt", ".md", ".pdf"}


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
    return "text/plain"


def validate_upload(filename: str, content: bytes, *, max_bytes: int) -> ValidatedUpload:
    """Ensure extension, size, and MIME type are acceptable for v1 intake."""
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
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

    content_hash = hashlib.sha256(content).hexdigest()
    provenance = {
        "original_filename": Path(filename).name,
        "content_hash_sha256": content_hash,
        "uploaded_at": datetime.now(tz=UTC).isoformat(),
        "mime_type": mime_type,
    }
    return ValidatedUpload(
        filename=Path(filename).name,
        mime_type=mime_type,
        byte_size=len(content),
        content_hash=content_hash,
        provenance=provenance,
    )
