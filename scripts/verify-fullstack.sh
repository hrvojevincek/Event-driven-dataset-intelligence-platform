#!/usr/bin/env bash
# Full-stack scaffold smoke test (KRE-128): backend health + frontend UI reachable.
#
# Prerequisites:
#   make dev   # or: docker compose up -d --build
#
# Optional env:
#   API_URL=http://localhost:8000
#   FRONTEND_URL=http://localhost:3000
#   TIMEOUT=120
#   INTERVAL=2
set -euo pipefail

API_URL="${API_URL:-http://localhost:8000}"
FRONTEND_URL="${FRONTEND_URL:-http://localhost:3000}"
TIMEOUT="${TIMEOUT:-120}"
INTERVAL="${INTERVAL:-2}"

die() {
  echo "ERROR: $*" >&2
  exit 1
}

wait_for_url() {
  local name="$1"
  local url="$2"
  local elapsed=0

  echo "Waiting for ${name} at ${url} (timeout ${TIMEOUT}s) ..."
  while (( elapsed < TIMEOUT )); do
    if curl -sf "${url}" >/dev/null 2>&1; then
      echo "  ${name} is up (${elapsed}s)"
      return 0
    fi
    sleep "${INTERVAL}"
    elapsed=$((elapsed + INTERVAL))
  done
  die "${name} not reachable at ${url} after ${TIMEOUT}s"
}

echo "=== EventForge full-stack smoke test (KRE-128) ==="
echo "API:      ${API_URL}"
echo "Frontend: ${FRONTEND_URL}"
echo

wait_for_url "Backend /health" "${API_URL}/health"

HEALTH_BODY="$(curl -sf "${API_URL}/health")"
python3 -c '
import json, sys
body = json.load(sys.stdin)
assert body.get("status") == "ok", body
print("  GET /health -> 200 {\"status\": \"ok\"}")
' <<<"${HEALTH_BODY}"

READY_BODY="$(curl -sf "${API_URL}/health/ready")"
python3 -c '
import json, sys
body = json.load(sys.stdin)
assert body.get("status") == "ready", body
assert body.get("checks", {}).get("postgres") == "ok", body
print("  GET /health/ready -> 200 postgres ok")
' <<<"${READY_BODY}"

wait_for_url "Frontend" "${FRONTEND_URL}"

FRONTEND_HTML="$(curl -sf "${FRONTEND_URL}/")"
python3 -c '
import sys
html = sys.stdin.read()
needles = ("EventForge", "Dataset intelligence")
missing = [n for n in needles if n not in html]
if missing:
    print("Frontend HTML missing:", ", ".join(missing), file=sys.stderr)
    sys.exit(1)
print("  GET / -> 200 (EventForge placeholder UI)")
' <<<"${FRONTEND_HTML}"

# Same origin path the browser api-client uses (NEXT_PUBLIC_API_URL defaults to localhost:8000).
CLIENT_HEALTH="$(curl -sf "${API_URL}/health")"
python3 -c '
import json, sys
body = json.load(sys.stdin)
assert body.get("status") == "ok", body
print("  api-client path OK (browser fetch to /health on API_URL)")
' <<<"${CLIENT_HEALTH}"

echo
echo "Full-stack smoke test passed."
