from unittest.mock import MagicMock, patch

from eventforge.db.models import Asset
from eventforge.services.preprocessing.extract import (
    SourceKind,
    _extract_pdf,
    source_kind_for_asset,
)
from eventforge.services.preprocessing.segmentation import (
    SourceKind as SegmentationSourceKind,
)
from eventforge.services.preprocessing.segmentation import (
    segment_text,
)


def _asset(filename: str, mime_type: str) -> Asset:
    return Asset(
        job_id="11111111-1111-4111-8111-111111111111",
        filename=filename,
        mime_type=mime_type,
        storage_uri=f"file:///tmp/{filename}",
    )


def test_source_kind_for_asset_pdf_and_markdown() -> None:
    assert source_kind_for_asset(_asset("report.pdf", "application/pdf")) == SourceKind.MARKDOWN
    assert source_kind_for_asset(_asset("notes.md", "text/markdown")) == SourceKind.MARKDOWN
    assert source_kind_for_asset(_asset("call_001.txt", "text/plain")) == SourceKind.PLAIN


def test_plain_text_uses_line_fallback_for_single_newlines() -> None:
    text = "Agent: Hello.\nCustomer: I need help.\nAgent: Sure thing."
    segments = segment_text(
        text,
        chunk_size=512,
        overlap=50,
        source_kind=SegmentationSourceKind.PLAIN,
    )
    assert len(segments) == 3
    assert segments[0].content == "Agent: Hello."


def test_markdown_reconstructs_hard_wrapped_pdf_lines() -> None:
    text = (
        "This is the first sentence of a long paragraph that was\n"
        "hard-wrapped by a PDF extractor across multiple lines.\n"
        "This is the second sentence. It should stay grouped.\n\n"
        "A second paragraph starts here."
    )
    segments = segment_text(
        text,
        chunk_size=512,
        overlap=50,
        source_kind=SegmentationSourceKind.MARKDOWN,
    )
    assert len(segments) == 2
    assert "hard-wrapped" in segments[0].content
    assert "second sentence" in segments[0].content
    assert segments[1].content == "A second paragraph starts here."


def test_markdown_splits_on_headers() -> None:
    text = (
        "# Introduction\n"
        "Opening context for the document.\n\n"
        "## Details\n"
        "More specific information lives here."
    )
    segments = segment_text(
        text,
        chunk_size=512,
        overlap=50,
        source_kind=SegmentationSourceKind.MARKDOWN,
    )
    assert len(segments) == 2
    assert segments[0].content.startswith("# Introduction")
    assert segments[1].content.startswith("## Details")


def test_markdown_does_not_emit_one_segment_per_physical_line() -> None:
    text = "\n".join(f"Line {index} continues the same block." for index in range(8))
    segments = segment_text(
        text,
        chunk_size=512,
        overlap=50,
        source_kind=SegmentationSourceKind.MARKDOWN,
    )
    assert len(segments) == 1
    assert "Line 0" in segments[0].content
    assert "Line 7" in segments[0].content


@patch("eventforge.services.preprocessing.extract.pymupdf4llm.to_markdown")
@patch("eventforge.services.preprocessing.extract.pymupdf.open")
def test_extract_pdf_uses_layout_aware_markdown(mock_open, mock_to_markdown) -> None:
    mock_doc = MagicMock()
    mock_open.return_value = mock_doc
    mock_to_markdown.return_value = "# Title\n\nBody paragraph."

    result = _extract_pdf(b"%PDF-1.4 mock")

    mock_open.assert_called_once()
    mock_to_markdown.assert_called_once_with(mock_doc)
    mock_doc.close.assert_called_once()
    assert result.startswith("# Title")
