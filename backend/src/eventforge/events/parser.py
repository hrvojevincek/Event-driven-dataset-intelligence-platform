import json
from typing import Any


def parse_eventbridge_sqs_body(body: str) -> dict[str, Any]:
    """Extract EventBridge detail from an SQS message body."""
    wrapper = json.loads(body)
    detail = wrapper["detail"]
    if isinstance(detail, str):
        return json.loads(detail)
    return detail


def parse_annotation_queue_message(body: str) -> tuple[dict[str, Any], str | None]:
    """Parse annotation queue payloads from EventBridge or Step Functions task tokens."""
    wrapper = json.loads(body)
    if "TaskToken" in wrapper:
        detail = wrapper.get("detail", wrapper.get("event"))
        if isinstance(detail, str):
            detail = json.loads(detail)
        if not isinstance(detail, dict):
            msg = "Step Functions SQS message missing event detail"
            raise ValueError(msg)
        return detail, wrapper["TaskToken"]

    return parse_eventbridge_sqs_body(body), None
