import uuid
from unittest.mock import patch

import pytest

from eventforge.core.config import Settings
from eventforge.events.schemas.constants import EMBEDDING_DIMENSION
from eventforge.services.legacy.embedding import get_embedding_client
from eventforge.services.mock.fixtures import deterministic_embedding


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
