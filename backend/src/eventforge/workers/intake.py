import logging
from typing import Any, ClassVar

from eventforge.core.config import get_settings
from eventforge.events.parser import parse_eventbridge_sqs_body
from eventforge.events.publisher import EVENT_SOURCE_INTAKE
from eventforge.events.schemas.constants import DETAIL_TYPE_PROJECT_SUBMITTED, WORKER_NAME_INTAKE
from eventforge.stages.intake import parse_project_submitted_event, run_intake
from eventforge.workers.bootstrap import main
from eventforge.workers.stage_worker import StageWorker

logger = logging.getLogger(__name__)


class IntakeWorker(StageWorker):
    """Consumes project.submitted events on the intake queue."""

    worker_name: ClassVar[str] = WORKER_NAME_INTAKE
    event_source: ClassVar[str] = EVENT_SOURCE_INTAKE

    def __init__(self) -> None:
        settings = get_settings()
        super().__init__(settings.intake_queue_name, settings)

    async def process_message(self, message: dict[str, Any]) -> None:
        detail = parse_eventbridge_sqs_body(message["Body"])
        detail_type = detail.get("detail_type")

        if detail_type != DETAIL_TYPE_PROJECT_SUBMITTED:
            msg = f"Unsupported detail_type on intake queue: {detail_type}"
            raise ValueError(msg)

        event = parse_project_submitted_event(detail)
        async with self._session_factory() as session:
            result = await run_intake(session, self._publisher, event)
        if result is None:
            logger.info(
                "Skipped duplicate project.submitted",
                extra={
                    "event_id": str(event.event_id),
                    "job_id": str(event.job_id),
                    "correlation_id": event.correlation_id,
                },
            )
            return
        logger.info(
            "Intake completed",
            extra={
                "event_id": str(event.event_id),
                "job_id": str(event.job_id),
                "correlation_id": event.correlation_id,
                "asset_count": result.payload.asset_count,
            },
        )


if __name__ == "__main__":
    main(IntakeWorker, service_suffix="intake")
