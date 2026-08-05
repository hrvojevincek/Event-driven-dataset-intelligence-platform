import hashlib
import json
import re

from eventforge.events.schemas.constants import EMBEDDING_DIMENSION

MOCK_MODEL = "mock-local"


def deterministic_embedding(text: str, *, dimension: int = EMBEDDING_DIMENSION) -> list[float]:
    """Stable pseudo-embedding from text so RAG queries return repeatable results."""
    seed = hashlib.sha256(text.encode()).digest()
    values: list[float] = []
    while len(values) < dimension:
        for byte in seed:
            values.append((byte / 127.5) - 1.0)
            if len(values) >= dimension:
                break
        seed = hashlib.sha256(seed).digest()
    return values


def _extract_labeled_line(content: str, label: str) -> str | None:
    prefix = f"{label}:"
    for line in content.splitlines():
        if line.startswith(prefix):
            return line[len(prefix) :].strip()
    return None


def mock_entity_extraction_json(user_content: str) -> str:
    """JSON array for knowledge entity extraction."""
    topic = _extract_labeled_line(user_content, "Research topic") or "research topic"
    return json.dumps(
        [
            {
                "name": topic[:120],
                "entity_type": "concept",
                "source_chunk_index": 0,
            },
            {
                "name": "async event pipelines",
                "entity_type": "concept",
                "source_chunk_index": 0,
            },
            {
                "name": "multi-agent orchestration",
                "entity_type": "concept",
                "source_chunk_index": 1,
            },
        ]
    )


def mock_sub_queries_json(user_content: str) -> str:
    """JSON array of research sub-queries, one per numbered entity line."""
    entity_lines = re.findall(r"^\d+\.\s+.+$", user_content, flags=re.MULTILINE)
    count = max(len(entity_lines), 1)
    queries = [
        f"How does mock research angle {index} apply to this topic?"
        for index in range(1, count + 1)
    ]
    return json.dumps(queries)


def mock_research_note_markdown(user_content: str) -> str:
    """Markdown research note for a single sub-query."""
    sub_query = _extract_labeled_line(user_content, "Sub-query") or "focused sub-query"
    topic = _extract_labeled_line(user_content, "Research topic") or "research topic"
    return (
        "## Key findings\n\n"
        f"Mock findings for **{sub_query}** in the context of {topic}.\n\n"
        "## Evidence summary\n\n"
        "- [RAG-0] Fixture evidence from ingested mock sources.\n"
        "- [WEB-0] Fixture web follow-up snippet (mock mode).\n\n"
        "## Open questions\n\n"
        "- None — generated locally without external API calls."
    )


def mock_synthesis_report_markdown(user_content: str) -> str:
    """Cited synthesis report for the full job."""
    topic = _extract_labeled_line(user_content, "Research topic") or "research topic"
    return (
        f"# Executive summary\n\n"
        f"Mock synthesis for **{topic}**. Pipeline ran in local mock mode "
        f"without Tavily or OpenAI charges.\n\n"
        "## Key findings\n\n"
        "- Event-driven stages decouple ingestion, embedding, and synthesis.\n"
        "- Mock fixtures exercise the full UI and SSE pipeline locally.\n\n"
        "## Analysis\n\n"
        "This report is deterministic fixture content for development and demos.\n\n"
        "## Conclusion\n\n"
        "Use `MOCK_EXTERNAL_APIS=false` when you need real provider output.\n\n"
        "## References\n\n"
        "- [SRC-0] Mock local source catalog entry"
    )
