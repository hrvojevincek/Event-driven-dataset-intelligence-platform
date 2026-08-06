"""Generate synthetic WAV fixtures for the audio pipeline."""

import math
import struct
import wave
from pathlib import Path

SAMPLE_RATE = 16000
OUT = Path(__file__).resolve().parents[1] / "fixtures" / "support-calls-audio"


def write_tone(path: Path, *, seconds: float, freq: float) -> None:
    """Write a mono PCM WAV sine tone."""
    frames = int(SAMPLE_RATE * seconds)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        for i in range(frames):
            sample = int(12000 * math.sin(2 * math.pi * freq * (i / SAMPLE_RATE)))
            wav.writeframes(struct.pack("<h", sample))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    write_tone(OUT / "call_001.wav", seconds=3.0, freq=440.0)
    write_tone(OUT / "call_002.wav", seconds=4.5, freq=523.25)
    print(f"Wrote fixtures under {OUT}")


if __name__ == "__main__":
    main()
