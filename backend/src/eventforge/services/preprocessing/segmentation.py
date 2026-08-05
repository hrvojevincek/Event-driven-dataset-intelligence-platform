"""Split extracted text into segments for annotation planning."""

from dataclasses import dataclass

import tiktoken

DEFAULT_ENCODING = "cl100k_base"


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
    encoding_name: str = DEFAULT_ENCODING,
) -> list[TextSegment]:
    """Split text into paragraph segments, using token windows for long paragraphs."""
    normalized = text.strip()
    if not normalized:
        return []

    if overlap >= chunk_size:
        msg = "segment overlap must be smaller than chunk_size"
        raise ValueError(msg)

    raw_chunks: list[tuple[str, int | None, int | None]] = []
    for paragraph in _split_paragraphs(normalized):
        start = normalized.find(paragraph)
        end = start + len(paragraph)
        if _token_count(paragraph, encoding_name) <= chunk_size:
            raw_chunks.append((paragraph, start, end))
            continue
        for sub in _token_windows(
            paragraph,
            chunk_size=chunk_size,
            overlap=overlap,
            encoding_name=encoding_name,
        ):
            sub_start = start + paragraph.find(sub) if sub in paragraph else None
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
    encoding_name: str = DEFAULT_ENCODING,
) -> list[str]:
    """Split text into overlapping token windows."""
    return [
        segment.content
        for segment in segment_text(
            text,
            chunk_size=chunk_size,
            overlap=overlap,
            encoding_name=encoding_name,
        )
    ]


def build_source_text(*, title: str, snippet: str) -> str:
    """Combine title and body text for legacy chunking helpers."""
    parts = [title.strip(), snippet.strip()]
    return "\n\n".join(part for part in parts if part)


def _split_paragraphs(text: str) -> list[str]:
    paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
    if paragraphs:
        return paragraphs
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines if lines else [text]


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
