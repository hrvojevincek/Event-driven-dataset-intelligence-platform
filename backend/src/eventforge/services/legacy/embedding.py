"""Legacy OpenAI embedding client for research pipeline code removed in Phases 5–6."""

import logging
import uuid

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from eventforge.core.config import Settings, get_settings
from eventforge.db.repositories.llm_usage import LLMUsageRepository
from eventforge.events.schemas.constants import EMBEDDING_DIMENSION, EMBEDDING_MODEL
from eventforge.services.resilience.cost_cap import assert_job_under_cost_cap
from eventforge.services.resilience.errors import is_retryable_openai_error
from eventforge.services.resilience.external_call import call_with_resilience

logger = logging.getLogger(__name__)


class EmbeddingClient:
    """OpenAI embedding API wrapper with optional usage logging."""

    def __init__(
        self,
        settings: Settings | None = None,
        session: AsyncSession | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._session = session
        if not self._settings.openai_api_key:
            msg = "OPENAI_API_KEY is not configured"
            raise ValueError(msg)
        self._client = AsyncOpenAI(api_key=self._settings.openai_api_key)

    async def embed_texts(
        self,
        texts: list[str],
        *,
        job_id: uuid.UUID,
        agent_name: str,
    ) -> list[list[float]]:
        if not texts:
            return []

        if self._session is not None:
            await assert_job_under_cost_cap(self._session, job_id, self._settings)

        model = EMBEDDING_MODEL

        async def _create_embeddings():
            return await self._client.embeddings.create(model=model, input=texts)

        response = await call_with_resilience(
            "openai",
            _create_embeddings,
            settings=self._settings,
            is_retryable=is_retryable_openai_error,
        )
        ordered = sorted(response.data, key=lambda item: item.index)
        embeddings = [item.embedding for item in ordered]

        for vector in embeddings:
            if len(vector) != EMBEDDING_DIMENSION:
                msg = f"Expected {EMBEDDING_DIMENSION}-dim embedding, got {len(vector)}"
                raise ValueError(msg)

        total_tokens = response.usage.total_tokens if response.usage else 0
        resolved_model = response.model or model
        cost_usd = self._settings.total_cost_for_tokens(
            resolved_model,
            total_tokens,
            0,
        )

        if self._session is not None:
            try:
                await LLMUsageRepository(self._session).log(
                    job_id=job_id,
                    agent_name=agent_name,
                    model=resolved_model,
                    input_tokens=total_tokens,
                    output_tokens=0,
                    cost_usd=cost_usd,
                )
            except Exception:
                logger.exception(
                    "Failed to log embedding usage",
                    extra={
                        "job_id": str(job_id),
                        "agent_name": agent_name,
                        "model": resolved_model,
                    },
                )
            else:
                await assert_job_under_cost_cap(self._session, job_id, self._settings)

        logger.info(
            "Embeddings created",
            extra={
                "job_id": str(job_id),
                "agent_name": agent_name,
                "model": resolved_model,
                "text_count": len(texts),
                "total_tokens": total_tokens,
            },
        )
        return embeddings


def get_embedding_client(session: AsyncSession | None = None) -> EmbeddingClient:
    """Build an embedding client, optionally bound to a DB session for usage logging."""
    settings = get_settings()
    if settings.use_mock_external_apis:
        from eventforge.services.mock.embedding import MockEmbeddingClient

        return MockEmbeddingClient(settings, session=session)  # type: ignore[return-value]
    return EmbeddingClient(settings=settings, session=session)
