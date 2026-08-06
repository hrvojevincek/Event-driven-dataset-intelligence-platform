"""Generate synthetic WAV fixtures for the audio pipeline.

Prefers macOS ``say`` + ``ffmpeg`` so fixtures contain real speech (Whisper/VAD
need speech, not sine tones). Falls back to tones only if those tools are missing.
"""

from __future__ import annotations

import math
import shutil
import struct
import subprocess
import tempfile
import wave
from pathlib import Path

SAMPLE_RATE = 16000
OUT = Path(__file__).resolve().parents[1] / "fixtures" / "support-calls-audio"

SCRIPTS = (
    (
        "call_001.wav",
        "Hello, I need help with my billing account. My invoice looks wrong.",
    ),
    (
        "call_002.wav",
        "Hi, I was charged twice for last month's subscription. Can you refund one?",
    ),
)


def write_tone(path: Path, *, seconds: float, freq: float) -> None:
    """Write a mono PCM WAV sine tone (not usable for ASR demos)."""
    frames = int(SAMPLE_RATE * seconds)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        for i in range(frames):
            sample = int(12000 * math.sin(2 * math.pi * freq * (i / SAMPLE_RATE)))
            wav.writeframes(struct.pack("<h", sample))


def write_speech(path: Path, text: str) -> None:
    """Synthesize spoken WAV via macOS say + ffmpeg (16 kHz mono PCM)."""
    say = shutil.which("say")
    ffmpeg = shutil.which("ffmpeg")
    if not say or not ffmpeg:
        msg = "say and ffmpeg are required to generate speech fixtures"
        raise RuntimeError(msg)

    with tempfile.TemporaryDirectory() as tmp:
        aiff = Path(tmp) / "speech.aiff"
        subprocess.run([say, "-v", "Samantha", "-o", str(aiff), text], check=True)
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-i",
                str(aiff),
                "-ac",
                "1",
                "-ar",
                str(SAMPLE_RATE),
                str(path),
            ],
            check=True,
            capture_output=True,
        )


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    can_speech = shutil.which("say") and shutil.which("ffmpeg")
    if can_speech:
        for filename, text in SCRIPTS:
            write_speech(OUT / filename, text)
        print(f"Wrote speech fixtures under {OUT}")
        return

    print("say/ffmpeg not found; writing sine tones (ASR will produce no segments)")
    write_tone(OUT / "call_001.wav", seconds=3.0, freq=440.0)
    write_tone(OUT / "call_002.wav", seconds=4.5, freq=523.25)
    print(f"Wrote tone fixtures under {OUT}")


if __name__ == "__main__":
    main()
