"""Audio asset detection and segment extraction for preprocessing."""

from pathlib import Path

from eventforge.db.models import Asset
from eventforge.services.preprocessing.asr import ASRProvider
from eventforge.services.preprocessing.audio_segments import AudioSegmentPiece, window_utterances
from eventforge.services.storage.local import LocalStorage


def is_audio_asset(asset: Asset) -> bool:
    """Return True when an asset should be transcribed rather than text-extracted."""
    extension = Path(asset.filename).suffix.lower()
    return asset.mime_type.startswith("audio/") or extension == ".wav"


def transcribe_asset_to_segments(
    asset: Asset,
    storage: LocalStorage,
    asr: ASRProvider,
    *,
    min_window_ms: int,
    max_window_ms: int,
) -> list[AudioSegmentPiece]:
    """Run ASR on a WAV asset and return windowed segment pieces."""
    path = storage.resolve_path(asset.storage_uri)
    utterances = asr.transcribe(path)
    if not utterances:
        msg = f"ASR produced no segments for {asset.filename}"
        raise ValueError(msg)

    pieces = window_utterances(
        utterances,
        asr_model=asr.model_name,
        min_window_ms=min_window_ms,
        max_window_ms=max_window_ms,
    )
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
