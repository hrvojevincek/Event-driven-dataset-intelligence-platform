import json
import uuid
from unittest.mock import patch

import pytest

from eventforge.core.config import Settings
from eventforge.events.schemas.constants import (
    EMBEDDING_DIMENSION,
    WORKER_NAME_KNOWLEDGE,
    WORKER_NAME_RESEARCH,
)
from eventforge.services.legacy.embedding import get_embedding_client
from eventforge.services.llm.client import get_llm_client
from eventforge.services.llm.types import LLMMessage
from eventforge.services.mock.fixtures import (
    deterministic_embedding,
    mock_entity_extraction_json,
    mock_sub_queries_json,
)


def test_use_mock_external_apis_defaults_true_in_local() -> None:
    settings = Settings(environment="local", mock_external_apis=None)
    assert settings.use_mock_external_apis is True


def test_use_mock_external_apis_defaults_false_in_prod() -> None:
    settings = Settings(environment="prod", mock_external_apis=None)
    assert settings.use_mock_external_apis is False


def test_use_mock_external_apis_explicit_override() -> None:
    settings = Settings(environment="local", mock_external_apis=False)
    assert settings.use_mock_external_apis is False


def test_mock_external_apis_empty_env_treated_as_auto() -> None:
    settings = Settings(environment="local", mock_external_apis="")
    assert settings.use_mock_external_apis is True


@pytest.mark.asyncio
async def test_mock_embedding_returns_correct_dimension() -> None:
    settings = Settings(environment="local", mock_external_apis=True)
    with patch("eventforge.services.legacy.embedding.get_settings", return_value=settings):
        client = get_embedding_client()

    vectors = await client.embed_texts(
        ["hello", "world"],
        job_id=uuid.uuid4(),
        agent_name="embedding",
    )

    assert len(vectors) == 2
    assert len(vectors[0]) == EMBEDDING_DIMENSION
    assert vectors[0] != vectors[1]


def test_deterministic_embedding_is_stable() -> None:
    first = deterministic_embedding("same text")
    second = deterministic_embedding("same text")
    assert first == second


@pytest.mark.asyncio
async def test_mock_llm_knowledge_returns_entity_json() -> None:
    settings = Settings(environment="local", mock_external_apis=True)
    with patch("eventforge.services.llm.client.get_settings", return_value=settings):
        client = get_llm_client()

    result = await client.complete(
        [
            LLMMessage(role="system", content="extract entities"),
            LLMMessage(
                role="user",
                content="Research topic: Graph databases\n\nContext blocks...",
            ),
        ],
        job_id=uuid.uuid4(),
        agent_name=WORKER_NAME_KNOWLEDGE,
    )

    data = json.loads(result.content)
    assert isinstance(data, list)
    assert data[0]["entity_type"] == "concept"


@pytest.mark.asyncio
async def test_mock_llm_research_sub_queries_returns_json_array() -> None:
    settings = Settings(environment="local", mock_external_apis=True)
    with patch("eventforge.services.llm.client.get_settings", return_value=settings):
        client = get_llm_client()

    user_prompt = (
        "Research topic: Agents\n\n"
        "Entities (generate one sub-query per row, same order):\n"
        "1. async pipelines (concept)\n"
        "2. orchestration (concept)\n"
    )
    result = await client.complete(
        [
            LLMMessage(
                role="system",
                content="Respond with a JSON array of strings only",
            ),
            LLMMessage(role="user", content=user_prompt),
        ],
        job_id=uuid.uuid4(),
        agent_name=WORKER_NAME_RESEARCH,
    )

    queries = json.loads(result.content)
    assert len(queries) == 2
    assert queries == json.loads(mock_sub_queries_json(user_prompt))


def test_mock_entity_extraction_json_is_valid() -> None:
    payload = mock_entity_extraction_json("Research topic: EventForge")
    parsed = json.loads(payload)
    assert len(parsed) >= 2
