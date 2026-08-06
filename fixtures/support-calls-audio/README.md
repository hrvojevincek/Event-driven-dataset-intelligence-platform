# Support call audio fixtures

Short spoken WAV files for the audio pipeline demo and local verify scripts.

| File | Content | Sample rate | Source |
|------|---------|-------------|--------|
| `call_001.wav` | Billing help request | 16 kHz mono PCM | macOS `say` (Samantha) → ffmpeg |
| `call_002.wav` | Double-charge refund request | 16 kHz mono PCM | macOS `say` (Samantha) → ffmpeg |

**License:** Public domain / project-owned — safe to commit and redistribute.

**Usage:** Submit with the **Support call (audio)** template (`schema_template=support_call_audio`, `domain=audio`).

> Sine tones are **not** usable for ASR: Whisper’s VAD drops them as non-speech and produces no segments.

Regenerate (requires `say` + `ffmpeg` on macOS):

```bash
python3 scripts/generate-audio-fixtures.py
```
