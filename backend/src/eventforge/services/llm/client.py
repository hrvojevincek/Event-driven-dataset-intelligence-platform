import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from eventforge.core.config import LLMProviderName, Settings, get_settings
from eventforge.core.otel import agent_span, set_event_attributes
from eventforge.db.repositories.llm_usage import LLMUsageRepository
from eventforge.services.llm.providers.anthropic import AnthropicProvider
from eventforge.services.llm.providers.base import LLMProvider
from eventforge.services.llm.providers.openai import OpenAIProvider
from eventforge.services.llm.types import LLMCompletionResult, LLMMessage
from eventforge.services.resilience.cost_cap import assert_job_under_cost_cap
from eventforge.services.resilience.errors import (
    is_retryable_anthropic_error,
    is_retryable_openai_error,
)
from eventforge.services.resilience.external_call import call_with_resilience

logger = logging.getLogger(__name__)


class LLMClient:
    """Unified chat completion client with optional usage logging."""

    def __init__(
        self,
        settings: Settings | None = None,
        session: AsyncSession | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._session = session
        self._providers: dict[LLMProviderName, LLMProvider] = {}

    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        job_id: uuid.UUID,
        agent_name: str,
        model: str | None = None,
        max_tokens: int | None = None,
    ) -> LLMCompletionResult:
        resolved_model = model or self._settings.llm_default_model
        provider_name = self._settings.resolve_llm_provider(resolved_model)
        provider = self._get_provider(provider_name)

        with agent_span(
            agent_name,
            "complete",
            job_id=str(job_id),
        ) as span:
            set_event_attributes(
                span, model=resolved_model, agent_name=agent_name)

            if self._session is not None:
                await assert_job_under_cost_cap(self._session, job_id, self._settings)

            is_retryable = (
                is_retryable_openai_error
                if provider_name == "openai"
                else is_retryable_anthropic_error
            )

            async def _complete() -> LLMCompletionResult:
                return await provider.complete(
                    messages,
                    model=resolved_model,
                    max_tokens=max_tokens,
                )

            result = await call_with_resilience(
                provider_name,
                _complete,
                settings=self._settings,
                is_retryable=is_retryable,
            )

            set_event_attributes(
                span,
                model=result.model,
                token_count=result.input_tokens + result.output_tokens,
            )

            if self._session is not None:
                try:
                    await LLMUsageRepository(self._session).log(
                        job_id=job_id,
                        agent_name=agent_name,
                        model=result.model,
                        input_tokens=result.input_tokens,
                        output_tokens=result.output_tokens,
                        cost_usd=result.cost_usd,
                    )
                except Exception:
                    logger.exception(
                        "Failed to log LLM usage; returning completion result",
                        extra={
                            "job_id": str(job_id),
                            "agent_name": agent_name,
                            "model": result.model,
                        },
                    )
                else:
                    await assert_job_under_cost_cap(self._session, job_id, self._settings)

            return result

    def _get_provider(self, provider_name: LLMProviderName) -> LLMProvider:
        if provider_name not in self._providers:
            if provider_name == "openai":
                self._providers[provider_name] = OpenAIProvider(self._settings)
            else:
                self._providers[provider_name] = AnthropicProvider(
                    self._settings)
        return self._providers[provider_name]


def get_llm_client(session: AsyncSession | None = None) -> LLMClient:
    """Build an LLM client, optionally bound to a DB session for usage logging."""
    settings = get_settings()
    return LLMClient(settings=settings, session=session)
