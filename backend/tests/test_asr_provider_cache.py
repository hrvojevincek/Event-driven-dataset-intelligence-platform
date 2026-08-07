"""Local faster-whisper provider is cached per process."""

import sys
from unittest.mock import MagicMock, patch

from eventforge.core.config import Settings
from eventforge.services.preprocessing.asr import get_asr_provider, reset_local_asr_cache


def test_get_asr_provider_reuses_local_model_instance() -> None:
    reset_local_asr_cache()
    settings = Settings(asr_provider="local", asr_local_model="tiny", asr_device="cpu")
    fake_model = MagicMock(name="WhisperModel")
    whisper_ctor = MagicMock(return_value=fake_model)
    fake_faster_whisper = MagicMock(WhisperModel=whisper_ctor)

    with patch.dict(sys.modules, {"faster_whisper": fake_faster_whisper}):
        first = get_asr_provider(settings)
        second = get_asr_provider(settings)

    assert first is second
    whisper_ctor.assert_called_once_with("tiny", device="cpu", compute_type="int8")
    reset_local_asr_cache()
