from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class LLMUsageCallResponse(BaseModel):
    """One logged LLM call for a project."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    agent_name: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    created_at: datetime


class LLMUsageSummaryResponse(BaseModel):
    """Aggregated LLM cost and per-call breakdown for a project."""

    total_cost_usd: float
    calls: list[LLMUsageCallResponse]
