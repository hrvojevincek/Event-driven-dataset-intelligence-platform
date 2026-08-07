"""LLM classification of support-call utterances as agent or customer."""

from __future__ import annotations

import json
import re
import uuid
from typing import Protocol

from eventforge.services.llm.client import LLMClient
from eventforge.services.llm.types import LLMMessage
from eventforge.services.preprocessing.asr import Utterance
from eventforge.services.preprocessing.audio_segments import SpeakerRole

_SPEAKER_ROLE_AGENT = "speaker_role"
_SPEAKER_SYSTEM = (
    "You classify support-call transcript lines as spoken by the agent or the customer. "
    "Respond with a JSON object only — no markdown fences or commentary. "
    'Shape: {"roles": {"0": "agent", "1": "customer", ...}}. '
    "Use string keys for each 0-based line index. "
    'Each value must be exactly "agent" or "customer". '
    "The agent typically greets, asks for account details, and offers products. "
    "The customer typically explains their issue and answers questions."
)


class SpeakerRoleClassifier(Protocol):
    """Assign agent/customer roles to timed ASR utterances."""

    async def classify(
        self,
        utterances: list[Utterance],
        *,
        job_id: uuid.UUID,
    ) -> list[SpeakerRole]:
        """Return one role per utterance in order."""
        ...


def _strip_fences(content: str) -> str:
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    return stripped


def _build_prompt(utterances: list[Utterance]) -> str:
    lines = [
        "Classify each transcript line as agent or customer.",
        "",
        "Transcript:",
    ]
    for index, utterance in enumerate(utterances):
        lines.append(f'{index}: "{utterance.text}"')
    return "\n".join(lines)


def _parse_roles(content: str, utterance_count: int) -> list[SpeakerRole]:
    try:
        parsed = json.loads(_strip_fences(content))
    except json.JSONDecodeError as exc:
        msg = "speaker role response must be valid JSON"
        raise ValueError(msg) from exc

    if not isinstance(parsed, dict):
        msg = "speaker role response must be a JSON object"
        raise ValueError(msg)

    raw_roles = parsed.get("roles")
    if not isinstance(raw_roles, dict):
        msg = 'speaker role response must include a "roles" object'
        raise ValueError(msg)

    roles: list[SpeakerRole] = []
    for index in range(utterance_count):
        value = raw_roles.get(str(index))
        if value not in ("agent", "customer"):
            msg = f"missing or invalid role for utterance index {index}"
            raise ValueError(msg)
        roles.append(value)
    return roles


class LLMSpeakerRoleClassifier:
    """Classify utterance speakers via the shared LLM client."""

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm_client = llm_client

    async def classify(
        self,
        utterances: list[Utterance],
        *,
        job_id: uuid.UUID,
    ) -> list[SpeakerRole]:
        if not utterances:
            return []

        result = await self._llm_client.complete(
            [
                LLMMessage(role="system", content=_SPEAKER_SYSTEM),
                LLMMessage(role="user", content=_build_prompt(utterances)),
            ],
            job_id=job_id,
            agent_name=_SPEAKER_ROLE_AGENT,
        )
        return _parse_roles(result.content, len(utterances))
