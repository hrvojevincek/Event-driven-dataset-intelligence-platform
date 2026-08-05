import json
import logging
import re
import uuid

from pydantic import BaseModel, Field, ValidationError

from eventforge.db.models import DocumentChunk, Job, KnowledgeEntity
from eventforge.events.schemas import WORKER_NAME_KNOWLEDGE
from eventforge.services.llm.client import LLMClient
from eventforge.services.llm.types import LLMMessage

logger = logging.getLogger(__name__)

_ENTITY_EXTRACTION_SYSTEM = (
    "You extract structured knowledge entities from research context. "
    "Respond with a JSON array only — no markdown fences or commentary. "
    "Each item must have: name (string), entity_type (string), "
    "source_chunk_index (integer index into the provided context blocks, or null)."
)


class ExtractedEntityItem(BaseModel):
    """One entity parsed from the LLM extraction response."""

    name: str = Field(min_length=1, max_length=512)
    entity_type: str = Field(min_length=1, max_length=64)
    source_chunk_index: int | None = Field(default=None, ge=0)


def _parse_entity_json(content: str) -> list[ExtractedEntityItem]:
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)

    data = json.loads(stripped)
    if not isinstance(data, list):
        msg = "Entity extraction response must be a JSON array"
        raise ValueError(msg)

    items: list[ExtractedEntityItem] = []
    for index, raw in enumerate(data):
        try:
            items.append(ExtractedEntityItem.model_validate(raw))
        except ValidationError as exc:
            logger.warning(
                "Skipping invalid entity extraction item",
                extra={"item_index": index, "errors": exc.errors()},
            )
    return items


def _build_extraction_prompt(job: Job, retrieved_chunks: list[DocumentChunk]) -> str:
    blocks: list[str] = [
        f"Research topic: {job.topic}",
        "",
        "Context blocks (use source_chunk_index to cite):",
    ]
    for index, chunk in enumerate(retrieved_chunks):
        blocks.extend(
            [
                f"[{index}]",
                chunk.content,
                "",
            ]
        )
    blocks.append(
        "Extract key entities and concepts relevant to the research topic. "
        "Prefer specific concepts over duplicating the topic string."
    )
    return "\n".join(blocks)


def _dedupe_items(items: list[ExtractedEntityItem]) -> list[ExtractedEntityItem]:
    seen: set[tuple[str, str]] = set()
    deduped: list[ExtractedEntityItem] = []
    for item in items:
        key = (item.name.lower(), item.entity_type.lower())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def build_knowledge_entities(
    job: Job,
    retrieved_chunks: list[DocumentChunk],
    extracted_items: list[ExtractedEntityItem],
    *,
    max_entities: int,
) -> list[KnowledgeEntity]:
    """Map LLM extraction output to ORM rows, always including a topic entity."""
    entities: list[KnowledgeEntity] = [
        KnowledgeEntity(
            job_id=job.id,
            chunk_id=None,
            name=job.topic[:512],
            entity_type="topic",
            task_index=0,
        )
    ]

    chunk_by_index = {index: chunk for index, chunk in enumerate(retrieved_chunks)}
    next_index = 1
    for item in extracted_items:
        if item.name.strip().lower() == job.topic.strip().lower() and item.entity_type == "topic":
            continue

        chunk_id: uuid.UUID | None = None
        if item.source_chunk_index is not None:
            source_chunk = chunk_by_index.get(item.source_chunk_index)
            if source_chunk is not None:
                chunk_id = source_chunk.id

        entities.append(
            KnowledgeEntity(
                job_id=job.id,
                chunk_id=chunk_id,
                name=item.name[:512],
                entity_type=item.entity_type[:64],
                task_index=next_index,
            )
        )
        next_index += 1

        if len(entities) >= max_entities:
            break

    return entities


async def extract_knowledge_entities(
    llm_client: LLMClient,
    job: Job,
    retrieved_chunks: list[DocumentChunk],
    *,
    max_entities: int,
) -> list[KnowledgeEntity]:
    """Run LLM entity extraction over RAG-retrieved chunks and build ORM entities."""
    if not retrieved_chunks:
        return build_knowledge_entities(job, [], [], max_entities=max_entities)

    prompt = _build_extraction_prompt(job, retrieved_chunks)
    result = await llm_client.complete(
        [
            LLMMessage(role="system", content=_ENTITY_EXTRACTION_SYSTEM),
            LLMMessage(role="user", content=prompt),
        ],
        job_id=job.id,
        agent_name=WORKER_NAME_KNOWLEDGE,
    )

    try:
        items = _dedupe_items(_parse_entity_json(result.content))
    except (json.JSONDecodeError, ValueError):
        logger.exception(
            "Entity extraction JSON parse failed; falling back to topic-only entities",
            extra={"job_id": str(job.id)},
        )
        items = []

    return build_knowledge_entities(job, retrieved_chunks, items, max_entities=max_entities)
