import logging
from typing import Any

from eventforge.core.config import get_settings
from eventforge.events.parser import parse_eventbridge_sqs_body
from eventforge.events.schemas.constants import DETAIL_TYPE_PREPROCESSING_COMPLETED
from eventforge.stages.planning import (
    parse_preprocessing_completed_event,
    run_planning,
)
from eventforge.workers.bootstrap import main
from eventforge.workers.stage_worker import StageWorker

logger = logging.getLogger(__name__)


class PlanningWorker(StageWorker):
    """Consumes preprocessing.completed events and runs the planning agent."""

    def __init__(self) -> None:
        settings = get_settings()
        super().__init__(settings.planning_queue_name, settings)

    async def handle_message(self, message: dict[str, Any]) -> None:
        detail = parse_eventbridge_sqs_body(message["Body"])
        detail_type = detail.get("detail_type")

        if detail_type != DETAIL_TYPE_PREPROCESSING_COMPLETED:
            msg = f"Unsupported detail_type on planning queue: {detail_type}"
            raise ValueError(msg)

        event = parse_preprocessing_completed_event(detail)
        async with self._session_factory() as session:
            result = await run_planning(session, self._publisher, event)

        if result is None:
            logger.info(
                "Skipped duplicate preprocessing.completed",
                extra={
                    "event_id": str(event.event_id),
                    "job_id": str(event.job_id),
                    "correlation_id": event.correlation_id,
                },
            )
            return

        logger.info(
            "Planning completed",
            extra={
                "event_id": str(event.event_id),
                "job_id": str(event.job_id),
                "correlation_id": event.correlation_id,
                "task_count": result.payload.task_count,
            },
        )


if __name__ == "__main__":
    main(PlanningWorker, service_suffix="planning")
