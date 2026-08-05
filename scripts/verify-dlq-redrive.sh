#!/usr/bin/env bash
# Verify worker queues have SQS redrive policies pointing at eventforge-dlq.
set -euo pipefail

ENDPOINT="${AWS_ENDPOINT_URL:-http://localhost:4566}"
REGION="${AWS_REGION:-eu-west-2}"
PREFIX="${SQS_QUEUE_PREFIX:-eventforge}"
MAX_RECEIVE_COUNT="${SQS_MAX_RECEIVE_COUNT:-3}"

WORKER_QUEUES=(intake preprocessing planning annotation export)

aws_cmd() {
  aws --endpoint-url="${ENDPOINT}" --region="${REGION}" "$@"
}

die() {
  echo "ERROR: $*" >&2
  exit 1
}

DLQ_URL="$(aws_cmd sqs get-queue-url --queue-name "${PREFIX}-dlq" --query 'QueueUrl' --output text 2>/dev/null)" \
  || die "DLQ queue ${PREFIX}-dlq not found. Is LocalStack running?"

DLQ_ARN="$(aws_cmd sqs get-queue-attributes \
  --queue-url "${DLQ_URL}" \
  --attribute-names QueueArn \
  --query 'Attributes.QueueArn' \
  --output text)"

echo "DLQ: ${PREFIX}-dlq (${DLQ_ARN})"
echo "Expected maxReceiveCount: ${MAX_RECEIVE_COUNT}"
echo

for queue in "${WORKER_QUEUES[@]}"; do
  queue_name="${PREFIX}-${queue}"
  queue_url="$(aws_cmd sqs get-queue-url --queue-name "${queue_name}" --query 'QueueUrl' --output text)"
  redrive_raw="$(aws_cmd sqs get-queue-attributes \
    --queue-url "${queue_url}" \
    --attribute-names RedrivePolicy \
    --query 'Attributes.RedrivePolicy' \
    --output text)"

  if [[ "${redrive_raw}" == "None" || -z "${redrive_raw}" ]]; then
    die "${queue_name}: missing RedrivePolicy"
  fi

  REDRIVE_RAW="${redrive_raw}" DLQ_ARN="${DLQ_ARN}" MAX_RECEIVE_COUNT="${MAX_RECEIVE_COUNT}" QUEUE_NAME="${queue_name}" PREFIX="${PREFIX}" \
    python3 -c '
import json, os, sys

redrive = json.loads(os.environ["REDRIVE_RAW"])
dlq_arn = os.environ["DLQ_ARN"]
max_count = int(os.environ["MAX_RECEIVE_COUNT"])
queue_name = os.environ["QUEUE_NAME"]
prefix = os.environ["PREFIX"]

if redrive.get("deadLetterTargetArn") != dlq_arn:
    print(f"{queue_name}: deadLetterTargetArn mismatch", file=sys.stderr)
    print(f"  expected: {dlq_arn}", file=sys.stderr)
    print("  got:     ", redrive.get("deadLetterTargetArn"), file=sys.stderr)
    sys.exit(1)

if int(redrive.get("maxReceiveCount", 0)) != max_count:
    print(f"{queue_name}: maxReceiveCount mismatch", file=sys.stderr)
    print(f"  expected: {max_count}", file=sys.stderr)
    print("  got:     ", redrive.get("maxReceiveCount"), file=sys.stderr)
    sys.exit(1)

print(f"OK  {queue_name} -> {prefix}-dlq (maxReceiveCount={max_count})")
'
done

echo
echo "All worker queues have DLQ redrive policies."
