#!/usr/bin/env bash
# Audio pipeline smoke test: WAV upload → ASR preprocessing → JSONL with timing fields.
#
# Prerequisites (all must be running):
#   docker compose up -d postgres localstack
#   uv sync --project backend --extra asr   # local faster-whisper (default)
#   uv run --project backend uvicorn eventforge.main:app --port 8000
#   make workers
#
# Optional env:
#   API_URL=http://localhost:8000
#   FIXTURE_FILE=fixtures/support-calls-audio/call_001.wav
#   SCHEMA_TEMPLATE=support_call_audio
#   ASR_PROVIDER=local|openai
#   POLL_INTERVAL=3
#   TIMEOUT=600                           # ASR on CPU can be slow
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_URL="${API_URL:-http://localhost:8000}"
SCHEMA_TEMPLATE="${SCHEMA_TEMPLATE:-support_call_audio}"
FIXTURE_FILE="${FIXTURE_FILE:-${ROOT}/fixtures/support-calls-audio/call_001.wav}"
POLL_INTERVAL="${POLL_INTERVAL:-3}"
TIMEOUT="${TIMEOUT:-600}"

die() {
  echo "ERROR: $*" >&2
  exit 1
}

[[ -f "${FIXTURE_FILE}" ]] || die "Fixture not found: ${FIXTURE_FILE} (run scripts/generate-audio-fixtures.py)"

echo "Checking API health at ${API_URL}/health ..."
curl -sf "${API_URL}/health" >/dev/null || die "API not reachable at ${API_URL}"

echo "Submitting audio project (template=${SCHEMA_TEMPLATE}, fixture=${FIXTURE_FILE}) ..."
RESPONSE="$(curl -sf -X POST "${API_URL}/api/v1/projects" \
  -F "name=Audio pipeline smoke test" \
  -F "schema_template=${SCHEMA_TEMPLATE}" \
  -F "files=@${FIXTURE_FILE};filename=call_001.wav;type=audio/wav")"

JOB_ID="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["job_id"])' <<<"${RESPONSE}")"
echo "Created job_id=${JOB_ID}"
echo "Polling project (timeout ${TIMEOUT}s) ..."

ELAPSED=0
DETAIL=""
while (( ELAPSED < TIMEOUT )); do
  DETAIL="$(curl -sf "${API_URL}/api/v1/projects/${JOB_ID}")"
  STATUS="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])' <<<"${DETAIL}")"

  if [[ "${STATUS}" == "completed" ]]; then
    break
  fi
  if [[ "${STATUS}" == "failed" ]]; then
    echo "${DETAIL}" | python3 -m json.tool
    die "Project failed before completion"
  fi

  STAGE_SUMMARY="$(python3 -c '
import json, sys
detail = json.load(sys.stdin)
parts = [s["stage"] + ":" + s["status"] for s in detail["stages"]]
print(" | ".join(parts))
' <<<"${DETAIL}")"
  echo "  [${ELAPSED}s] project=${STATUS}  ${STAGE_SUMMARY}"

  sleep "${POLL_INTERVAL}"
  ELAPSED=$((ELAPSED + POLL_INTERVAL))
done

FINAL_STATUS="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])' <<<"${DETAIL}")"
[[ "${FINAL_STATUS}" == "completed" ]] || die "Timed out or failed (status=${FINAL_STATUS})"

echo "Verifying JSONL export includes audio timing fields ..."
EXPORT_BODY="$(curl -sf "${API_URL}/api/v1/projects/${JOB_ID}/export?format=jsonl")"
python3 -c '
import json, sys

body = sys.stdin.read().strip()
if not body:
    print("Export body is empty", file=sys.stderr)
    sys.exit(1)

lines = [line for line in body.splitlines() if line.strip()]
if not lines:
    print("No JSONL rows", file=sys.stderr)
    sys.exit(1)

row = json.loads(lines[0])
for key in ("audio_uri", "start_ms", "end_ms", "content", "labels", "provenance"):
    if key not in row:
        print(f"Missing export field: {key}", file=sys.stderr)
        sys.exit(1)

print(f"  GET /export -> {len(lines)} row(s)")
print("  audio_uri=" + str(row["audio_uri"]))
print("  start_ms=" + str(row["start_ms"]) + " end_ms=" + str(row["end_ms"]))
print("  content=" + repr(row["content"][:80]) + "...")
' <<<"${EXPORT_BODY}"

echo "Audio pipeline smoke test passed."
