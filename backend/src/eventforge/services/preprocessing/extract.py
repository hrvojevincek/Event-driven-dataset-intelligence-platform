"""Extract plain text from uploaded assets."""

from io import BytesIO
from pathlib import Path

from pypdf import PdfReader

from eventforge.db.models import Asset
from eventforge.services.storage.local import LocalStorage

TEXT_EXTENSIONS = {".txt", ".md"}


def extract_text_from_bytes(content: bytes, *, mime_type: str, filename: str) -> str:
    """Return normalized plain text for a supported upload type."""
    extension = Path(filename).suffix.lower()
    if mime_type == "application/pdf" or extension == ".pdf":
        return _extract_pdf(content)
    if mime_type.startswith("text/") or extension in TEXT_EXTENSIONS:
        return _extract_plain_text(content)
    msg = f"Unsupported mime type for extraction: {mime_type}"
    raise ValueError(msg)


def read_asset_text(asset: Asset, storage: LocalStorage) -> str:
    """Load an asset from local storage and extract its text content."""
    path = storage.resolve_path(asset.storage_uri)
    content = path.read_bytes()
    return extract_text_from_bytes(
        content,
        mime_type=asset.mime_type,
        filename=asset.filename,
    )


def _extract_plain_text(content: bytes) -> str:
    return content.decode("utf-8", errors="replace").strip()


def _extract_pdf(content: bytes) -> str:
    reader = PdfReader(BytesIO(content))
    parts: list[str] = []
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            parts.append(page_text.strip())
    text = "\n\n".join(parts).strip()
    if not text:
        msg = "PDF contains no extractable text"
        raise ValueError(msg)
    return text
