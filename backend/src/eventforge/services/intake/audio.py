"""WAV validation helpers for audio intake."""

import io
import wave


def probe_wav_duration_seconds(content: bytes) -> float:
    """Return duration of a PCM WAV file in seconds."""
    with wave.open(io.BytesIO(content), "rb") as wav_file:
        frame_rate = wav_file.getframerate()
        if frame_rate <= 0:
            msg = "Invalid WAV: sample rate must be positive"
            raise ValueError(msg)
        return wav_file.getnframes() / frame_rate
