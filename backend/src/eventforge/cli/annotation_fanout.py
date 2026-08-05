"""One-shot ECS task entrypoint for the Step Functions annotation fan-out prepare step."""

import asyncio
import json
import logging
import os
import sys
from typing import Any

from eventforge.core.config import get_settings
from eventforge.db.session import get_session_factory
from eventforge.services.step_functions import send_task_failure, send_task_success
from eventforge.stages.annotation import parse_planning_completed_event, prepare_annotation_fanout

logger = logging.getLogger(__name__)


async def _run_prepare() -> dict[str, Any]:
    task_token = os.environ.get("STEP_FUNCTIONS_TASK_TOKEN", "").strip()
    if not task_token:
        msg = "STEP_FUNCTIONS_TASK_TOKEN is required"
        raise ValueError(msg)

    event_json = os.environ.get("PLANNING_COMPLETED_EVENT", "").strip()
    if not event_json:
        msg = "PLANNING_COMPLETED_EVENT is required"
        raise ValueError(msg)

    detail = json.loads(event_json)
    event = parse_planning_completed_event(detail)
    settings = get_settings()
    session_factory = get_session_factory(settings)

    async with session_factory() as session:
        result = await prepare_annotation_fanout(session, event)

    if result is None:
        output = {
            "job_id": str(event.job_id),
            "correlation_id": event.correlation_id,
            "tasks": [],
            "skipped": True,
        }
    else:
        output = {
            "job_id": str(event.job_id),
            "correlation_id": event.correlation_id,
            "tasks": [task.model_dump(mode="json") for task in result],
            "skipped": False,
        }

    send_task_success(task_token, output, settings)
    return output


def main() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    task_token = os.environ.get("STEP_FUNCTIONS_TASK_TOKEN", "").strip()
    try:
        output = asyncio.run(_run_prepare())
        logger.info(
            "Annotation fan-out prepared for Step Functions",
            extra={
                "job_id": output["job_id"],
                "task_count": len(output["tasks"]),
                "skipped": output["skipped"],
            },
        )
    except Exception as exc:
        logger.exception("Annotation fan-out prepare step failed")
        if task_token:
            send_task_failure(task_token, error=type(exc).__name__, cause=str(exc))
        sys.exit(1)


if __name__ == "__main__":
    main()
