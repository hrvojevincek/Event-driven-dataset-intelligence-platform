import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from eventforge.core.config import Settings, get_settings
from eventforge.db.models import DocumentChunk, Job, KnowledgeEntity, Source
from eventforge.db.repositories import DocumentChunkRepository, SourceRepository
from eventforge.events.schemas.constants import WORKER_NAME_RESEARCH
from eventforge.services.legacy.embedding import EmbeddingClient
from eventforge.services.llm.client import LLMClient
from eventforge.services.llm.types import LLMMessage
from eventforge.services.search.tavily import (
    TavilyClient,
    get_tavily_client,
    resolve_tavily_search_depth,
)
from eventforge.services.search.types import WebSearchResult

logger = logging.getLogger(__name__)

_RESEARCH_NOTE_SYSTEM = (
    "You are a research analyst synthesizing findings for one focused sub-query. "
    "Write clear markdown with sections: Key findings, Evidence summary, Open questions. "
    "Cite ingested context inline as [RAG-n] and web follow-up as [WEB-n]. "
    "Stay grounded in the provided sources; do not invent citations."
)


def _build_note_prompt(
    job: Job,
    sub_query: str,
    focus_entity: KnowledgeEntity | None,
    rag_chunks: list[DocumentChunk],
    sources_by_id: dict[uuid.UUID, Source],
    web_results: list[WebSearchResult],
) -> str:
    lines = [
        f"Research topic: {job.topic}",
        f"Sub-query: {sub_query}",
    ]
    if focus_entity is not None:
        lines.append(f"Focus entity: {focus_entity.name} ({focus_entity.entity_type})")
    lines.extend(["", "Ingested context (cite as [RAG-n]):"])

    if rag_chunks:
        for index, chunk in enumerate(rag_chunks):
            source = sources_by_id.get(chunk.source_id)
            source_label = source.title if source is not None else "Unknown source"
            lines.extend(
                [
                    f"[RAG-{index}] ({source_label})",
                    chunk.content,
                    "",
                ]
            )
    else:
        lines.append("(No ingested chunks retrieved for this sub-query.)")
        lines.append("")

    lines.append("Web follow-up (cite as [WEB-n]):")
    if web_results:
        for index, result in enumerate(web_results):
            lines.extend(
                [
                    f"[WEB-{index}] {result.title} — {result.url}",
                    result.snippet,
                    "",
                ]
            )
    else:
        lines.append("(No web follow-up results.)")
        lines.append("")

    lines.append("Synthesize focused findings that answer the sub-query using the sources above.")
    return "\n".join(lines)


async def _retrieve_rag_chunks(
    session: AsyncSession,
    embed_client: EmbeddingClient,
    job: Job,
    sub_query: str,
    *,
    top_k: int,
) -> tuple[list[DocumentChunk], dict[uuid.UUID, Source]]:
    chunk_repo = DocumentChunkRepository(session)
    vectors = await embed_client.embed_texts(
        [sub_query],
        job_id=job.id,
        agent_name=WORKER_NAME_RESEARCH,
    )
    chunks = await chunk_repo.search_similar(job.id, vectors[0], limit=top_k)

    source_ids = {chunk.source_id for chunk in chunks}
    sources = await SourceRepository(session).list_by_ids(list(source_ids))
    sources_by_id = {source.id: source for source in sources}
    return chunks, sources_by_id


async def _optional_web_follow_up(
    search_client: TavilyClient,
    settings: Settings,
    job: Job,
    sub_query: str,
) -> list[WebSearchResult]:
    if not settings.use_mock_external_apis and not settings.tavily_api_key:
        return []

    try:
        return await search_client.search(
            sub_query,
            max_results=settings.research_tavily_max_results,
            search_depth=resolve_tavily_search_depth(job.depth),
        )
    except Exception:
        logger.exception(
            "Tavily follow-up failed; continuing with RAG context only",
            extra={"job_id": str(job.id), "sub_query_length": len(sub_query)},
        )
        return []


async def generate_research_note(
    session: AsyncSession,
    llm_client: LLMClient,
    embed_client: EmbeddingClient,
    job: Job,
    sub_query: str,
    focus_entity: KnowledgeEntity | None,
    *,
    search_client: TavilyClient | None = None,
    settings: Settings | None = None,
) -> str:
    """Synthesize a research note from RAG context and optional Tavily follow-up."""
    resolved_settings = settings or get_settings()
    client = search_client or get_tavily_client(resolved_settings)

    rag_chunks, sources_by_id = await _retrieve_rag_chunks(
        session,
        embed_client,
        job,
        sub_query,
        top_k=resolved_settings.research_rag_top_k,
    )
    web_results = await _optional_web_follow_up(client, resolved_settings, job, sub_query)

    prompt = _build_note_prompt(
        job,
        sub_query,
        focus_entity,
        rag_chunks,
        sources_by_id,
        web_results,
    )
    result = await llm_client.complete(
        [
            LLMMessage(role="system", content=_RESEARCH_NOTE_SYSTEM),
            LLMMessage(role="user", content=prompt),
        ],
        job_id=job.id,
        agent_name=WORKER_NAME_RESEARCH,
    )
    return result.content.strip()
