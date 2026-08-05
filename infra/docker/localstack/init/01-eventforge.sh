#!/bin/bash
# Bootstrap EventForge AWS resources in LocalStack
set -euo pipefail

MAX_RECEIVE_COUNT="${SQS_MAX_RECEIVE_COUNT:-3}"
PREFIX="${SQS_QUEUE_PREFIX:-eventforge}"
EVENT_BUS_NAME="${EVENT_BUS_NAME:-eventforge-bus}"
WORKER_QUEUES=(intake preprocessing planning annotation export)

configure_redrive_policy() {
  local queue_name="$1"
  local queue_url attributes_json

  awslocal sqs create-queue --queue-name "${queue_name}" >/dev/null 2>&1 || true

  queue_url="$(awslocal sqs get-queue-url --queue-name "${queue_name}" --query 'QueueUrl' --output text)"

  attributes_json="$(DLQ_ARN="${DLQ_ARN}" MAX_RECEIVE_COUNT="${MAX_RECEIVE_COUNT}" python3 -c '
import json, os

redrive = {
    "deadLetterTargetArn": os.environ["DLQ_ARN"],
    "maxReceiveCount": int(os.environ["MAX_RECEIVE_COUNT"]),
}
print(json.dumps({"RedrivePolicy": json.dumps(redrive)}))
')"

  awslocal sqs set-queue-attributes \
    --queue-url "${queue_url}" \
    --attributes "${attributes_json}"
}

queue_arn() {
  local queue_name="$1"
  local queue_url

  queue_url="$(awslocal sqs get-queue-url --queue-name "${queue_name}" --query 'QueueUrl' --output text)"
  awslocal sqs get-queue-attributes \
    --queue-url "${queue_url}" \
    --attribute-names QueueArn \
    --query 'Attributes.QueueArn' \
    --output text
}

wire_event_to_queue() {
  local rule_name="$1"
  local detail_type="$2"
  local queue_name="$3"
  local target_id="$4"
  local arn

  arn="$(queue_arn "${queue_name}")"

  awslocal events put-rule \
    --name "${rule_name}" \
    --event-bus-name "${EVENT_BUS_NAME}" \
    --event-pattern "{\"detail-type\":[\"${detail_type}\"]}" \
    || true

  awslocal events put-targets \
    --rule "${rule_name}" \
    --event-bus-name "${EVENT_BUS_NAME}" \
    --targets "Id=${target_id},Arn=${arn}" \
    || true
}

awslocal events create-event-bus --name "${EVENT_BUS_NAME}" || true

awslocal sqs create-queue --queue-name "${PREFIX}-dlq" >/dev/null 2>&1 || true

DLQ_QUEUE_URL="$(awslocal sqs get-queue-url --queue-name "${PREFIX}-dlq" --query 'QueueUrl' --output text)"
DLQ_ARN="$(awslocal sqs get-queue-attributes \
  --queue-url "${DLQ_QUEUE_URL}" \
  --attribute-names QueueArn \
  --query 'Attributes.QueueArn' \
  --output text)"

for queue in "${WORKER_QUEUES[@]}"; do
  configure_redrive_policy "${PREFIX}-${queue}"
done

wire_event_to_queue \
  eventforge-project-submitted-to-intake \
  eventforge.project.submitted \
  "${PREFIX}-intake" \
  intake-queue

wire_event_to_queue \
  eventforge-intake-completed-to-preprocessing \
  eventforge.intake.completed \
  "${PREFIX}-preprocessing" \
  preprocessing-queue

wire_event_to_queue \
  eventforge-preprocessing-completed-to-planning \
  eventforge.preprocessing.completed \
  "${PREFIX}-planning" \
  planning-queue

wire_event_to_queue \
  eventforge-planning-completed-to-annotation \
  eventforge.planning.completed \
  "${PREFIX}-annotation" \
  annotation-orchestrator-queue

wire_event_to_queue \
  eventforge-annotation-task-dispatched-to-annotation \
  eventforge.annotation.task.dispatched \
  "${PREFIX}-annotation" \
  annotation-dispatch-queue

wire_event_to_queue \
  eventforge-annotation-task-completed-to-export \
  eventforge.annotation.task.completed \
  "${PREFIX}-export" \
  export-queue

wire_event_to_queue \
  eventforge-annotation-all-completed-to-export \
  eventforge.annotation.all_completed \
  "${PREFIX}-export" \
  export-all-queue

echo "EventForge LocalStack resources initialized (bus=${EVENT_BUS_NAME}, prefix=${PREFIX}, DLQ redrive maxReceiveCount=${MAX_RECEIVE_COUNT})."
