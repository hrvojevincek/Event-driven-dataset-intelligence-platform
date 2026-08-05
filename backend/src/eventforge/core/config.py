from decimal import Decimal
from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from eventforge.core.llm_pricing import DEFAULT_MODEL_PRICING, ModelPricing, compute_cost_usd

LLMProviderName = Literal["openai", "anthropic"]


class Settings(BaseSettings):
    """Application configuration loaded from environment variables and .env."""
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: str = "local"
    log_level: str = "INFO"
    mock_external_apis: bool | None = None

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "eventforge"
    postgres_user: str = "eventforge"
    postgres_password: str = "changeme"

    cors_origins: list[str] = Field(default=["http://localhost:3000"])

    aws_region: str = "eu-west-2"
    aws_endpoint_url: str | None = "http://localhost:4566"
    aws_access_key_id: str = "test"
    aws_secret_access_key: str = "test"
    event_bus_name: str = "eventforge-bus"
    sqs_queue_prefix: str = "eventforge"
    sqs_wait_time_seconds: int = 20
    sqs_max_messages: int = 10
    sqs_max_receive_count: int = 3

    openai_api_key: str = ""
    anthropic_api_key: str = ""
    tavily_api_key: str = ""
    llm_default_model: str = "gpt-4o-mini"
    llm_max_output_tokens: int = 4096
    preprocessing_segment_size_tokens: int = 512
    preprocessing_segment_overlap_tokens: int = 50
    knowledge_rag_top_k: int = 10
    knowledge_max_entities: int = 4
    research_rag_top_k: int = 8
    research_tavily_max_results: int = 3
    llm_max_retries: int = 3
    llm_retry_base_delay_seconds: float = 1.0
    llm_retry_max_delay_seconds: float = 30.0
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_recovery_timeout_seconds: float = 60.0
    job_max_cost_usd: Decimal | None = None
    llm_model_pricing: dict[str, ModelPricing] = Field(
        default_factory=lambda: DEFAULT_MODEL_PRICING.copy()
    )

    otel_enabled: bool = True
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"
    otel_service_name: str = "eventforge-api"

    research_orchestration_mode: Literal["local", "step_functions"] = "local"

    upload_root: str = "data/uploads"
    max_upload_file_bytes: int = 50 * 1024 * 1024
    max_upload_files_per_project: int = 50

    @field_validator("mock_external_apis", mode="before")
    @classmethod
    def _empty_mock_flag(cls, value: object) -> object:
        if value == "":
            return None
        return value

    @field_validator(
        "openai_api_key",
        "anthropic_api_key",
        "tavily_api_key",
        "postgres_password",
        mode="before",
    )
    @classmethod
    def _strip_secret_whitespace(cls, value: object) -> object:
        """Strip trailing newlines/spaces from Secrets Manager and .env values."""
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator(
        "llm_max_retries",
        "circuit_breaker_failure_threshold",
    )
    @classmethod
    def _non_negative_int(cls, value: int) -> int:
        if value < 0:
            msg = "must be >= 0"
            raise ValueError(msg)
        return value

    @field_validator(
        "llm_retry_base_delay_seconds",
        "llm_retry_max_delay_seconds",
        "circuit_breaker_recovery_timeout_seconds",
    )
    @classmethod
    def _positive_float(cls, value: float) -> float:
        if value <= 0:
            msg = "must be > 0"
            raise ValueError(msg)
        return value

    @field_validator("job_max_cost_usd")
    @classmethod
    def _positive_cost_cap(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and value <= 0:
            msg = "must be > 0 when set"
            raise ValueError(msg)
        return value

    @model_validator(mode="after")
    def _retry_delays_ordered(self) -> Self:
        if self.llm_retry_base_delay_seconds > self.llm_retry_max_delay_seconds:
            msg = "llm_retry_base_delay_seconds must not exceed llm_retry_max_delay_seconds"
            raise ValueError(msg)
        return self

    @property
    def use_mock_external_apis(self) -> bool:
        """Use fixture Tavily/LLM/embeddings instead of paid external APIs."""
        if self.mock_external_apis is not None:
            return self.mock_external_apis
        return self.environment == "local"

    @property
    def ingestion_queue_name(self) -> str:
        return f"{self.sqs_queue_prefix}-ingestion"

    @property
    def embedding_queue_name(self) -> str:
        return f"{self.sqs_queue_prefix}-embedding"

    @property
    def knowledge_mining_queue_name(self) -> str:
        return f"{self.sqs_queue_prefix}-knowledge-mining"

    @property
    def research_queue_name(self) -> str:
        return f"{self.sqs_queue_prefix}-research"

    @property
    def synthesis_queue_name(self) -> str:
        return f"{self.sqs_queue_prefix}-synthesis"

    @property
    def dlq_queue_name(self) -> str:
        return f"{self.sqs_queue_prefix}-dlq"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def async_database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    def resolve_llm_provider(self, model: str) -> LLMProviderName:
        normalized = model.lower()
        if normalized.startswith("claude"):
            return "anthropic"
        if normalized.startswith(("gpt-", "o1", "o3", "text-embedding")):
            return "openai"
        msg = f"Cannot resolve LLM provider for model: {model}"
        raise ValueError(msg)

    def total_cost_for_tokens(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> Decimal:
        return compute_cost_usd(
            model,
            input_tokens,
            output_tokens,
            self.llm_model_pricing,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
