"""Extract plain text from uploaded assets."""

from enum import StrEnum
from pathlib import Path

import pymupdf
import pymupdf4llm

from eventforge.db.models import Asset
from eventforge.services.storage.local import LocalStorage

TEXT_EXTENSIONS = {".txt", ".md"}
MARKDOWN_MIME_TYPES = {"text/markdown", "text/x-markdown"}


class SourceKind(StrEnum):
    """Segmentation strategy for an extracted document."""

    PLAIN = "plain"
    MARKDOWN = "markdown"


def source_kind_for_asset(asset: Asset) -> SourceKind:
    """Choose segmentation rules from asset filename and MIME type."""
    extension = Path(asset.filename).suffix.lower()
    if asset.mime_type == "application/pdf" or extension == ".pdf":
        return SourceKind.MARKDOWN
    if extension == ".md" or asset.mime_type in MARKDOWN_MIME_TYPES:
        return SourceKind.MARKDOWN
    return SourceKind.PLAIN


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
    """Extract layout-aware Markdown from a PDF via PyMuPDF."""
    doc = pymupdf.open(stream=content, filetype="pdf")
    try:
        markdown = pymupdf4llm.to_markdown(doc)
    finally:
        doc.close()
    text = markdown.strip()
    if not text:
        msg = "PDF contains no extractable text"
        raise ValueError(msg)
    return text
