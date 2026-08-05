import logging
from typing import Any

from eventforge.agents.export import (
    parse_annotation_all_completed_event,
    process_annotation_all_completed,
)
from eventforge.core.config import get_settings
from eventforge.db.session import get_session_factory
from eventforge.events.parser import parse_eventbridge_sqs_body
from eventforge.events.publisher import EventPublisher
from eventforge.events.schemas.constants import (
    DETAIL_TYPE_ANNOTATION_ALL_COMPLETED,
    DETAIL_TYPE_ANNOTATION_TASK_COMPLETED,
)
from eventforge.workers.base import SqsConsumer
from eventforge.workers.bootstrap import main
from eventforge.workers.cost_cap import run_with_cost_cap_handling

logger = logging.getLogger(__name__)


class ExportWorker(SqsConsumer):
    """Consumes annotation.all_completed events and runs the export agent."""

    def __init__(self) -> None:
        settings = get_settings()
        super().__init__(settings.synthesis_queue_name, settings)
        self._publisher = EventPublisher(settings)
        self._session_factory = get_session_factory(settings)

    async def handle_message(self, message: dict[str, Any]) -> None:
        detail = parse_eventbridge_sqs_body(message["Body"])
        detail_type = detail.get("detail_type")

        if detail_type == DETAIL_TYPE_ANNOTATION_TASK_COMPLETED:
            logger.info(
                "Skipping annotation.task.completed; export waits for annotation.all_completed",
                extra={
                    "event_id": detail.get("event_id"),
                    "job_id": detail.get("job_id"),
                },
            )
            return

        if detail_type == DETAIL_TYPE_ANNOTATION_ALL_COMPLETED:
            await self._handle_annotation_all_completed(detail)
            return

        msg = f"Unexpected detail_type for export worker: {detail_type}"
        raise ValueError(msg)

    async def _handle_annotation_all_completed(self, detail: dict[str, Any]) -> None:
        event = parse_annotation_all_completed_event(detail)

        async def _process():
            async with self._session_factory() as session:
                return await process_annotation_all_completed(session, self._publisher, event)

        result = await run_with_cost_cap_handling(
            self._session_factory,
            self._publisher,
            detail,
            _process,
        )

        if result is None:
            logger.info(
                "Skipped export trigger",
                extra={
                    "event_id": str(event.event_id),
                    "job_id": str(event.job_id),
                    "correlation_id": event.correlation_id,
                },
            )
            return

        logger.info(
            "Export completed",
            extra={
                "event_id": str(event.event_id),
                "job_id": str(event.job_id),
                "correlation_id": event.correlation_id,
                "export_id": str(result.payload.export_id),
                "batch_count": result.payload.batch_count,
            },
        )


if __name__ == "__main__":
    main(ExportWorker, service_suffix="export")
