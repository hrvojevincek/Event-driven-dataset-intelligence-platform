#!/usr/bin/env bash
# Wait until LocalStack is healthy and EventForge SQS queues exist.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

ENDPOINT="${AWS_ENDPOINT_URL:-http://localhost:4566}"
REGION="${AWS_REGION:-us-east-1}"
PREFIX="${SQS_QUEUE_PREFIX:-eventforge}"
QUEUES=(
  "${PREFIX}-dlq"
  "${PREFIX}-ingestion"
  "${PREFIX}-embedding"
  "${PREFIX}-knowledge-mining"
  "${PREFIX}-research"
  "${PREFIX}-synthesis"
)

echo "Waiting for LocalStack at ${ENDPOINT}..."
for _ in $(seq 1 90); do
  if curl -sf "${ENDPOINT}/_localstack/health" | grep -q '"sqs": "running"'; then
    break
  fi
  sleep 1
done

if ! curl -sf "${ENDPOINT}/_localstack/health" | grep -q '"sqs": "running"'; then
  echo "LocalStack SQS is not running at ${ENDPOINT}" >&2
  exit 1
fi

for queue in "${QUEUES[@]}"; do
  echo "Waiting for queue ${queue}..."
  for _ in $(seq 1 90); do
    if AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID:-test}" \
      AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY:-test}" \
      aws --endpoint-url="${ENDPOINT}" --region="${REGION}" \
      sqs get-queue-url --queue-name "${queue}" >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done

  if ! AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID:-test}" \
    AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY:-test}" \
    aws --endpoint-url="${ENDPOINT}" --region="${REGION}" \
    sqs get-queue-url --queue-name "${queue}" >/dev/null 2>&1; then
    echo "Queue ${queue} not found after timeout" >&2
    exit 1
  fi
done

echo "LocalStack ready (${#QUEUES[@]} queues)."
