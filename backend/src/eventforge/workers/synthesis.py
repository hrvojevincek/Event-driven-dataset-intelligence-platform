import logging
from typing import Any

from eventforge.agents.synthesis import (
    parse_research_all_completed_event,
    parse_research_task_completed_event,
    process_research_all_completed,
    process_research_task_completed,
)
from eventforge.core.config import get_settings
from eventforge.db.session import get_session_factory
from eventforge.events.parser import parse_eventbridge_sqs_body
from eventforge.events.publisher import EventPublisher
from eventforge.events.schemas.constants import (
    DETAIL_TYPE_ANNOTATION_ALL_COMPLETED,
    DETAIL_TYPE_ANNOTATION_TASK_COMPLETED,
    DETAIL_TYPE_RESEARCH_ALL_COMPLETED,
)
from eventforge.workers.base import SqsConsumer
from eventforge.workers.bootstrap import main
from eventforge.workers.cost_cap import run_with_cost_cap_handling

logger = logging.getLogger(__name__)


class SynthesisWorker(SqsConsumer):
    """Consumes research completion events and runs the synthesis agent."""

    def __init__(self) -> None:
        settings = get_settings()
        super().__init__(settings.synthesis_queue_name, settings)
        self._settings = settings
        self._publisher = EventPublisher(settings)
        self._session_factory = get_session_factory(settings)

    async def handle_message(self, message: dict[str, Any]) -> None:
        detail = parse_eventbridge_sqs_body(message["Body"])
        detail_type = detail.get("detail_type")

        # Phase 6 emits annotation.* onto this queue; export lands in Phase 7.
        if detail_type in (
            DETAIL_TYPE_ANNOTATION_TASK_COMPLETED,
            DETAIL_TYPE_ANNOTATION_ALL_COMPLETED,
        ):
            logger.info(
                "Skipping annotation completion; export worker lands in Phase 7",
                extra={
                    "event_id": detail.get("event_id"),
                    "job_id": detail.get("job_id"),
                    "detail_type": detail_type,
                },
            )
            return

        if detail_type == DETAIL_TYPE_RESEARCH_ALL_COMPLETED:
            await self._handle_research_all_completed(detail)
            return

        if self._settings.research_orchestration_mode == "step_functions":
            logger.info(
                "Skipping research.task.completed; synthesis waits for research.all_completed",
                extra={
                    "event_id": detail.get("event_id"),
                    "job_id": detail.get("job_id"),
                },
            )
            return

        await self._handle_research_task_completed(detail)

    async def _handle_research_task_completed(self, detail: dict[str, Any]) -> None:
        event = parse_research_task_completed_event(detail)

        async def _process():
            async with self._session_factory() as session:
                return await process_research_task_completed(session, self._publisher, event)

        result = await run_with_cost_cap_handling(
            self._session_factory,
            self._publisher,
            detail,
            _process,
        )

        if result is None:
            logger.info(
                "Skipped synthesis trigger",
                extra={
                    "event_id": str(event.event_id),
                    "job_id": str(event.job_id),
                    "correlation_id": event.correlation_id,
                    "task_index": event.payload.task_index,
                },
            )
            return

        logger.info(
            "Synthesis completed",
            extra={
                "event_id": str(event.event_id),
                "job_id": str(event.job_id),
                "correlation_id": event.correlation_id,
                "report_id": str(result.payload.report_id),
                "note_count": result.payload.note_count,
            },
        )

    async def _handle_research_all_completed(self, detail: dict[str, Any]) -> None:
        event = parse_research_all_completed_event(detail)

        async def _process():
            async with self._session_factory() as session:
                return await process_research_all_completed(session, self._publisher, event)

        result = await run_with_cost_cap_handling(
            self._session_factory,
            self._publisher,
            detail,
            _process,
        )

        if result is None:
            logger.info(
                "Skipped synthesis trigger",
                extra={
                    "event_id": str(event.event_id),
                    "job_id": str(event.job_id),
                    "correlation_id": event.correlation_id,
                },
            )
            return

        logger.info(
            "Synthesis completed",
            extra={
                "event_id": str(event.event_id),
                "job_id": str(event.job_id),
                "correlation_id": event.correlation_id,
                "report_id": str(result.payload.report_id),
                "note_count": result.payload.note_count,
            },
        )


if __name__ == "__main__":
    main(SynthesisWorker, service_suffix="synthesis")
