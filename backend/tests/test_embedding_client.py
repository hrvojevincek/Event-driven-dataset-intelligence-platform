import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from eventforge.core.config import Settings
from eventforge.events.schemas.constants import EMBEDDING_DIMENSION
from eventforge.services.legacy.embedding import EmbeddingClient
from eventforge.services.preprocessing.segmentation import build_source_text, chunk_text


def test_build_source_text_joins_title_and_snippet() -> None:
    text = build_source_text(title="Title", snippet="Body text")
    assert text == "Title\n\nBody text"


def test_chunk_text_returns_single_chunk_for_short_text() -> None:
    text = "Short snippet about vectors."
    chunks = chunk_text(text, chunk_size=512, overlap=50)
    assert chunks == [text]


def test_chunk_text_splits_long_token_sequences() -> None:
    text = "word " * 400
    chunks = chunk_text(text, chunk_size=100, overlap=20)
    assert len(chunks) > 1
    assert all(chunk.strip() for chunk in chunks)


def test_chunk_text_rejects_overlap_gte_chunk_size() -> None:
    with pytest.raises(ValueError, match="overlap"):
        chunk_text("hello", chunk_size=10, overlap=10)


@pytest.mark.asyncio
async def test_embedding_client_raises_when_api_key_missing() -> None:
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        EmbeddingClient(Settings(openai_api_key=""))


@pytest.mark.asyncio
async def test_embedding_client_returns_vectors_and_logs_usage() -> None:
    settings = Settings(
        openai_api_key="test-openai",
        job_max_cost_usd=None,
    )
    session = AsyncMock()
    client = EmbeddingClient(settings, session=session)

    embedding_item = MagicMock()
    embedding_item.index = 0
    embedding_item.embedding = [0.1] * EMBEDDING_DIMENSION
    response = MagicMock()
    response.data = [embedding_item]
    response.model = "text-embedding-3-small"
    response.usage.total_tokens = 42

    mock_openai = AsyncMock()
    mock_openai.embeddings.create = AsyncMock(return_value=response)
    client._client = mock_openai

    async def _await_operation(_key, operation, **_kwargs):
        return await operation()

    with (
        patch(
            "eventforge.services.legacy.embedding.LLMUsageRepository",
        ) as mock_repo_cls,
        patch(
            "eventforge.services.legacy.embedding.call_with_resilience",
            side_effect=_await_operation,
        ),
    ):
        mock_repo = AsyncMock()
        mock_repo_cls.return_value = mock_repo
        vectors = await client.embed_texts(
            ["hello world"],
            job_id=uuid.uuid4(),
            agent_name="embedding",
        )

    assert len(vectors) == 1
    assert len(vectors[0]) == EMBEDDING_DIMENSION
    mock_repo.log.assert_awaited_once()
    logged = mock_repo.log.await_args.kwargs
    assert logged["input_tokens"] == 42
    assert logged["output_tokens"] == 0
    assert logged["cost_usd"] == Decimal("0.00000084")
