"""Local faster-whisper provider is cached per process."""

from unittest.mock import MagicMock, patch

from eventforge.core.config import Settings
from eventforge.services.preprocessing.asr import get_asr_provider, reset_local_asr_cache


def test_get_asr_provider_reuses_local_model_instance() -> None:
    reset_local_asr_cache()
    settings = Settings(asr_provider="local", asr_local_model="tiny", asr_device="cpu")
    fake_model = MagicMock(name="WhisperModel")

    with patch(
        "faster_whisper.WhisperModel",
        return_value=fake_model,
    ) as ctor:
        first = get_asr_provider(settings)
        second = get_asr_provider(settings)

    assert first is second
    ctor.assert_called_once_with("tiny", device="cpu", compute_type="int8")
    reset_local_asr_cache()
