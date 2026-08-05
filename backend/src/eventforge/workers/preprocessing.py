import logging
from typing import Any

from eventforge.core.config import get_settings
from eventforge.events.parser import parse_eventbridge_sqs_body
from eventforge.events.schemas.constants import DETAIL_TYPE_INTAKE_COMPLETED
from eventforge.stages.preprocessing import parse_intake_completed_event, run_preprocessing
from eventforge.workers.bootstrap import main
from eventforge.workers.stage_worker import StageWorker

logger = logging.getLogger(__name__)


class PreprocessingWorker(StageWorker):
    """Consumes intake.completed events and runs the preprocessing agent."""

    def __init__(self) -> None:
        settings = get_settings()
        super().__init__(settings.preprocessing_queue_name, settings)

    async def handle_message(self, message: dict[str, Any]) -> None:
        detail = parse_eventbridge_sqs_body(message["Body"])
        detail_type = detail.get("detail_type")

        if detail_type != DETAIL_TYPE_INTAKE_COMPLETED:
            msg = f"Unsupported detail_type on preprocessing queue: {detail_type}"
            raise ValueError(msg)

        event = parse_intake_completed_event(detail)
        async with self._session_factory() as session:
            result = await run_preprocessing(session, self._publisher, event)

        if result is None:
            logger.info(
                "Skipped duplicate intake.completed",
                extra={
                    "event_id": str(event.event_id),
                    "job_id": str(event.job_id),
                    "correlation_id": event.correlation_id,
                },
            )
            return

        logger.info(
            "Preprocessing completed",
            extra={
                "event_id": str(event.event_id),
                "job_id": str(event.job_id),
                "correlation_id": event.correlation_id,
                "segment_count": result.payload.segment_count,
            },
        )


if __name__ == "__main__":
    main(PreprocessingWorker, service_suffix="preprocessing")
