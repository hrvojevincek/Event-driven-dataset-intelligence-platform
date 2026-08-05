import json

from eventforge.events.parser import parse_annotation_queue_message


def test_parse_annotation_queue_message_eventbridge_wrapper() -> None:
    detail = {
        "event_id": "00000000-0000-4000-8000-000000000001",
        "detail_type": "eventforge.annotation.task.dispatched",
        "payload": {"task_id": "00000000-0000-4000-8000-000000000002"},
    }
    body = json.dumps({"detail": detail})

    parsed, token = parse_annotation_queue_message(body)

    assert parsed == detail
    assert token is None


def test_parse_annotation_queue_message_step_functions_token() -> None:
    detail = {
        "event_id": "00000000-0000-4000-8000-000000000001",
        "detail_type": "eventforge.annotation.task.dispatched",
        "payload": {"task_id": "00000000-0000-4000-8000-000000000002"},
    }
    body = json.dumps({"TaskToken": "abc123", "detail": detail})

    parsed, token = parse_annotation_queue_message(body)

    assert parsed == detail
    assert token == "abc123"
