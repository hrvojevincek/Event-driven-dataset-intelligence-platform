"""Split extracted text into segments for annotation planning."""

import re
from dataclasses import dataclass

import tiktoken

from eventforge.services.preprocessing.extract import SourceKind

DEFAULT_ENCODING = "cl100k_base"
_MARKDOWN_HEADER_SPLIT = re.compile(r"(?=^#{1,6}\s)", re.MULTILINE)


@dataclass(frozen=True)
class TextSegment:
    """One preprocessed text slice with optional source offsets."""

    content: str
    start_offset: int | None
    end_offset: int | None
    segment_index: int


def segment_text(
    text: str,
    *,
    chunk_size: int,
    overlap: int,
    source_kind: SourceKind = SourceKind.PLAIN,
    encoding_name: str = DEFAULT_ENCODING,
) -> list[TextSegment]:
    """Split text into segments using a strategy suited to the source format."""
    normalized = text.strip()
    if not normalized:
        return []

    if overlap >= chunk_size:
        msg = "segment overlap must be smaller than chunk_size"
        raise ValueError(msg)

    raw_chunks: list[tuple[str, int | None, int | None]] = []
    for block in _split_blocks(normalized, source_kind):
        start = normalized.find(block)
        end = start + len(block)
        if _token_count(block, encoding_name) <= chunk_size:
            raw_chunks.append((block, start, end))
            continue
        for sub in _token_windows(
            block,
            chunk_size=chunk_size,
            overlap=overlap,
            encoding_name=encoding_name,
        ):
            sub_start = start + block.find(sub) if sub in block else None
            sub_end = sub_start + len(sub) if sub_start is not None else None
            raw_chunks.append((sub, sub_start, sub_end))

    return [
        TextSegment(content=content, start_offset=start, end_offset=end, segment_index=index)
        for index, (content, start, end) in enumerate(raw_chunks)
    ]


def chunk_text(
    text: str,
    *,
    chunk_size: int,
    overlap: int,
    source_kind: SourceKind = SourceKind.PLAIN,
    encoding_name: str = DEFAULT_ENCODING,
) -> list[str]:
    """Split text into overlapping token windows."""
    return [
        segment.content
        for segment in segment_text(
            text,
            chunk_size=chunk_size,
            overlap=overlap,
            source_kind=source_kind,
            encoding_name=encoding_name,
        )
    ]


def build_source_text(*, title: str, snippet: str) -> str:
    """Combine title and body text for legacy chunking helpers."""
    parts = [title.strip(), snippet.strip()]
    return "\n\n".join(part for part in parts if part)


def _split_blocks(text: str, source_kind: SourceKind) -> list[str]:
    if source_kind == SourceKind.MARKDOWN:
        return _split_markdown_blocks(text)
    return _split_plain_blocks(text)


def _split_plain_blocks(text: str) -> list[str]:
    """Paragraph-first splitting with per-line fallback for utterance-style transcripts."""
    if "\n\n" in text:
        return [part.strip() for part in text.split("\n\n") if part.strip()]
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines if lines else [text]


def _split_markdown_blocks(text: str) -> list[str]:
    """Header-aware splitting with paragraph reconstruction for PDF/Markdown."""
    blocks: list[str] = []
    for section in _split_markdown_sections(text):
        paragraphs = [part.strip() for part in section.split("\n\n") if part.strip()]
        if paragraphs:
            blocks.extend(paragraphs)
            continue
        reconstructed = _reconstruct_paragraphs(section)
        if reconstructed:
            blocks.extend(reconstructed)
    return blocks if blocks else _reconstruct_paragraphs(text)


def _split_markdown_sections(text: str) -> list[str]:
    parts = [part.strip() for part in _MARKDOWN_HEADER_SPLIT.split(text) if part.strip()]
    return parts if parts else [text]


def _reconstruct_paragraphs(text: str) -> list[str]:
    """Merge hard-wrapped PDF lines into coherent paragraph blocks."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return []

    paragraphs: list[str] = []
    buffer: list[str] = []

    for line in lines:
        if line.startswith("#"):
            if buffer:
                paragraphs.append(" ".join(buffer))
                buffer = []
            paragraphs.append(line)
            continue

        if not buffer:
            buffer.append(line)
            continue

        if _starts_new_paragraph(buffer[-1], line):
            paragraphs.append(" ".join(buffer))
            buffer = [line]
        else:
            buffer.append(line)

    if buffer:
        paragraphs.append(" ".join(buffer))
    return paragraphs


def _starts_new_paragraph(previous: str, current: str) -> bool:
    if current.startswith("#"):
        return True
    if previous.endswith((".", "!", "?", ":", '"', "'")):
        return bool(current) and current[0].isupper()
    return False


def _token_count(text: str, encoding_name: str) -> int:
    encoder = tiktoken.get_encoding(encoding_name)
    return len(encoder.encode(text))


def _token_windows(
    text: str,
    *,
    chunk_size: int,
    overlap: int,
    encoding_name: str,
) -> list[str]:
    normalized = text.strip()
    if not normalized:
        return []

    encoder = tiktoken.get_encoding(encoding_name)
    tokens = encoder.encode(normalized)
    if len(tokens) <= chunk_size:
        return [normalized]

    chunks: list[str] = []
    start = 0
    while start < len(tokens):
        end = min(start + chunk_size, len(tokens))
        chunks.append(encoder.decode(tokens[start:end]))
        if end >= len(tokens):
            break
        start = end - overlap
    return chunks
