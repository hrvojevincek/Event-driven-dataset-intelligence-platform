#!/usr/bin/env bash
# End-to-end pipeline smoke test: POST /api/v1/projects → poll until export completes.
#
# Prerequisites (all must be running):
#   docker compose up -d postgres localstack
#   uv run --project backend uvicorn eventforge.main:app --port 8000
#   make workers   # or: make workers-overmind
#
# Optional env:
#   API_URL=http://localhost:8000
#   FIXTURE_FILE=path/to/transcript.txt   # default: generated temp file
#   SCHEMA_TEMPLATE=support_call
#   POLL_INTERVAL=2
#   TIMEOUT=300                           # annotation LLM calls may be slow
set -euo pipefail

API_URL="${API_URL:-http://localhost:8000}"
SCHEMA_TEMPLATE="${SCHEMA_TEMPLATE:-support_call}"
POLL_INTERVAL="${POLL_INTERVAL:-2}"
TIMEOUT="${TIMEOUT:-300}"

die() {
  echo "ERROR: $*" >&2
  exit 1
}

cleanup() {
  if [[ -n "${TEMP_FIXTURE:-}" && -f "${TEMP_FIXTURE}" ]]; then
    rm -f "${TEMP_FIXTURE}"
  fi
}
trap cleanup EXIT

if [[ -n "${FIXTURE_FILE:-}" ]]; then
  [[ -f "${FIXTURE_FILE}" ]] || die "FIXTURE_FILE not found: ${FIXTURE_FILE}"
  UPLOAD_PATH="${FIXTURE_FILE}"
else
  TEMP_FIXTURE="$(mktemp)"
  cat >"${TEMP_FIXTURE}" <<'EOF'
Customer: I was charged twice on my last bill and I need this fixed today.
Agent: I'm sorry about that. Let me pull up your account and review the duplicate charge.
Customer: Thank you — it's the enterprise plan from March.
Agent: I see the duplicate. I'll issue a refund and confirm by email within 24 hours.
EOF
  UPLOAD_PATH="${TEMP_FIXTURE}"
fi

echo "Checking API health at ${API_URL}/health ..."
curl -sf "${API_URL}/health" >/dev/null || die "API not reachable at ${API_URL}"

echo "Submitting project to ${API_URL}/api/v1/projects (template=${SCHEMA_TEMPLATE}) ..."
RESPONSE="$(curl -sf -X POST "${API_URL}/api/v1/projects" \
  -F "name=E2E pipeline smoke test" \
  -F "schema_template=${SCHEMA_TEMPLATE}" \
  -F "files=@${UPLOAD_PATH};filename=call_001.txt;type=text/plain")"

JOB_ID="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["job_id"])' <<<"${RESPONSE}")"
CORR_ID="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["correlation_id"])' <<<"${RESPONSE}")"
ASSET_COUNT="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["asset_count"])' <<<"${RESPONSE}")"

echo "Created job_id=${JOB_ID} correlation_id=${CORR_ID} asset_count=${ASSET_COUNT}"
echo "Polling ${API_URL}/api/v1/projects/${JOB_ID} (timeout ${TIMEOUT}s, interval ${POLL_INTERVAL}s) ..."

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

if [[ -z "${DETAIL}" ]]; then
  die "No project detail received"
fi

FINAL_STATUS="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])' <<<"${DETAIL}")"
if [[ "${FINAL_STATUS}" != "completed" ]]; then
  echo "${DETAIL}" | python3 -m json.tool
  die "Timed out after ${TIMEOUT}s (project status: ${FINAL_STATUS})"
fi

python3 -c '
import json, sys

detail = json.load(sys.stdin)
expected = ("intake", "preprocessing", "planning", "annotation", "export")
stages = {s["stage"]: s["status"] for s in detail["stages"]}

if detail["status"] != "completed":
    print("Expected project status completed, got", detail["status"], file=sys.stderr)
    sys.exit(1)

for name in expected:
    status = stages.get(name)
    if status != "completed":
        print(f"Expected stage {name} completed, got {status!r}", file=sys.stderr)
        sys.exit(1)

export = detail.get("dataset_export")
if export is None:
    print("Expected dataset_export on completed project", file=sys.stderr)
    sys.exit(1)

print("All pipeline stages completed:")
for name in expected:
    print(f"  - {name}: completed")
print("export lines:", export.get("line_count"))
print("job_id=" + detail["job_id"] + " correlation_id=" + detail["correlation_id"])
' <<<"${DETAIL}"

echo "Verifying JSONL export download ..."
EXPORT_BODY="$(curl -sf "${API_URL}/api/v1/projects/${JOB_ID}/export?format=jsonl")"
python3 -c '
import sys
body = sys.stdin.read().strip()
if not body:
    print("Export body is empty", file=sys.stderr)
    sys.exit(1)
lines = [line for line in body.splitlines() if line.strip()]
print(f"  GET /export -> {len(lines)} JSONL line(s)")
' <<<"${EXPORT_BODY}"

echo "E2E pipeline smoke test passed."
