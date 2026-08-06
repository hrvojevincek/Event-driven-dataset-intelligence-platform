# Support call audio fixtures

Short synthetic WAV files for the audio pipeline demo and local verify scripts.

| File | Duration | Sample rate | Source |
|------|----------|-------------|--------|
| `call_001.wav` | 3.0 s | 16 kHz mono PCM | Generated sine tone (440 Hz) |
| `call_002.wav` | 4.5 s | 16 kHz mono PCM | Generated sine tone (523 Hz) |

**License:** Public domain / project-owned — safe to commit and redistribute.

**Usage:** Submit with the **Support call (audio)** template (`schema_template=support_call_audio`, `domain=audio`). ASR (Phase 2) will transcribe these tones; labels come from the shared support-call schema.

Regenerate:

```bash
python3 scripts/generate-audio-fixtures.py
```

Or from repo root:

```bash
python3 - <<'PY'
# same as scripts/generate-audio-fixtures.py
PY
```
