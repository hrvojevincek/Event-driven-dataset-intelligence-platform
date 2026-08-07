"""Audio asset detection and segment extraction for preprocessing."""

from __future__ import annotations

import uuid
from pathlib import Path

from eventforge.core.otel import agent_span
from eventforge.db.models import Asset
from eventforge.services.preprocessing.asr import ASRProvider
from eventforge.services.preprocessing.audio_segments import AudioSegmentPiece, build_speaker_turns
from eventforge.services.preprocessing.speaker_roles import SpeakerRoleClassifier
from eventforge.services.storage.local import LocalStorage


def is_audio_asset(asset: Asset) -> bool:
    """Return True when an asset should be transcribed rather than text-extracted."""
    extension = Path(asset.filename).suffix.lower()
    return asset.mime_type.startswith("audio/") or extension == ".wav"


async def transcribe_asset_to_segments(
    asset: Asset,
    storage: LocalStorage,
    asr: ASRProvider,
    role_classifier: SpeakerRoleClassifier,
    *,
    job_id: uuid.UUID,
    max_turn_ms: int,
) -> list[AudioSegmentPiece]:
    """Run ASR on a WAV asset and return speaker-turn segment pieces."""
    path = storage.resolve_path(asset.storage_uri)
    utterances = asr.transcribe(path)
    if not utterances:
        msg = f"ASR produced no segments for {asset.filename}"
        raise ValueError(msg)

    with agent_span("asr", "speaker_role") as span:
        span.set_attribute("asr.utterance_count", len(utterances))
        roles = await role_classifier.classify(utterances, job_id=job_id)
        span.set_attribute("asr.role_count", len(roles))

    with agent_span("asr", "turn_merge") as span:
        span.set_attribute("asr.utterance_count", len(utterances))
        pieces = build_speaker_turns(
            utterances,
            roles,
            asr_model=asr.model_name,
            max_turn_ms=max_turn_ms,
        )
        span.set_attribute("asr.segment_count", len(pieces))
    if not pieces:
        msg = f"ASR produced no segmentable transcript for {asset.filename}"
        raise ValueError(msg)

    return [
        AudioSegmentPiece(
            content=piece.content,
            start_ms=piece.start_ms,
            end_ms=piece.end_ms,
            segment_index=piece.segment_index,
            metadata_json={
                **piece.metadata_json,
                "raw_utterance_count": len(utterances),
            },
        )
        for piece in pieces
    ]
