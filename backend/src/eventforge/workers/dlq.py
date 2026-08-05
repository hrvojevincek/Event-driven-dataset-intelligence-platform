import logging
from typing import Any

from eventforge.core.config import get_settings
from eventforge.events.parser import parse_eventbridge_sqs_body
from eventforge.services.pipeline_failure import parse_failed_event_detail, process_pipeline_failure
from eventforge.workers.bootstrap import main
from eventforge.workers.stage_worker import StageWorker

logger = logging.getLogger(__name__)


class DlqWorker(StageWorker):
    """Consumes poison messages from the DLQ and emits pipeline.failed events."""

    def __init__(self) -> None:
        settings = get_settings()
        super().__init__(settings.dlq_queue_name, settings)

    async def handle_message(self, message: dict[str, Any]) -> None:
        try:
            detail = parse_eventbridge_sqs_body(message["Body"])
            failed_event = parse_failed_event_detail(detail)
        except ValueError:
            logger.exception(
                "Poison pill DLQ message; discarding",
                extra={"message_id": message.get("MessageId")},
            )
            return

        receive_count_raw = message.get(
            "Attributes", {}).get("ApproximateReceiveCount")
        receive_count = int(receive_count_raw) if receive_count_raw else None

        async with self._session_factory() as session:
            result = await process_pipeline_failure(
                session,
                self._publisher,
                failed_event=failed_event,
                receive_count=receive_count,
            )

        if result is None:
            logger.info(
                "Skipped duplicate DLQ pipeline failure",
                extra={
                    "failed_event_id": str(failed_event.event_id),
                    "job_id": str(failed_event.job_id),
                    "correlation_id": failed_event.correlation_id,
                },
            )
            return

        logger.info(
            "Pipeline failure recorded",
            extra={
                "failed_event_id": str(failed_event.event_id),
                "job_id": str(failed_event.job_id),
                "correlation_id": failed_event.correlation_id,
                "stage": result.payload.stage,
                "failed_detail_type": result.payload.failed_detail_type,
            },
        )


if __name__ == "__main__":
    main(DlqWorker, service_suffix="dlq")
