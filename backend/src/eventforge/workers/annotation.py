import logging
from typing import Any

from eventforge.core.config import get_settings
from eventforge.events.parser import parse_annotation_queue_message
from eventforge.events.schemas.constants import (
    DETAIL_TYPE_ANNOTATION_TASK_DISPATCHED,
    DETAIL_TYPE_PLANNING_COMPLETED,
)
from eventforge.stages.annotation import (
    parse_annotation_task_dispatched_event,
    parse_planning_completed_event,
    run_annotation_fanout,
    run_annotation_task,
)
from eventforge.workers.bootstrap import main
from eventforge.workers.cost_cap import run_with_cost_cap_handling
from eventforge.workers.stage_worker import StageWorker

logger = logging.getLogger(__name__)


class AnnotationWorker(StageWorker):
    """Consumes planning.completed and annotation.task.dispatched events."""

    def __init__(self) -> None:
        settings = get_settings()
        super().__init__(settings.annotation_queue_name, settings)

    async def handle_message(self, message: dict[str, Any]) -> None:
        detail, task_token = parse_annotation_queue_message(message["Body"])
        detail_type = detail.get("detail_type")

        if detail_type == DETAIL_TYPE_PLANNING_COMPLETED:
            if self._settings.research_orchestration_mode == "step_functions":
                logger.info(
                    "Skipping planning.completed; Step Functions handles fan-out",
                    extra={
                        "event_id": detail.get("event_id"),
                        "job_id": detail.get("job_id"),
                    },
                )
                return
            await self._handle_planning_completed(detail)
            return

        if detail_type == DETAIL_TYPE_ANNOTATION_TASK_DISPATCHED:
            await self._handle_annotation_task_dispatched(detail, task_token)
            return

        msg = f"Unexpected detail_type for annotation worker: {detail_type}"
        raise ValueError(msg)

    async def _handle_planning_completed(self, detail: dict[str, Any]) -> None:
        event = parse_planning_completed_event(detail)

        async def _process():
            async with self._session_factory() as session:
                return await run_annotation_fanout(session, self._publisher, event)

        result = await run_with_cost_cap_handling(
            self._session_factory,
            self._publisher,
            detail,
            _process,
        )

        if result is None:
            logger.info(
                "Skipped duplicate planning.completed fan-out",
                extra={
                    "event_id": str(event.event_id),
                    "job_id": str(event.job_id),
                    "correlation_id": event.correlation_id,
                },
            )
            return

        logger.info(
            "Annotation tasks dispatched",
            extra={
                "event_id": str(event.event_id),
                "job_id": str(event.job_id),
                "correlation_id": event.correlation_id,
                "task_count": len(result),
            },
        )

    async def _handle_annotation_task_dispatched(
        self, detail: dict[str, Any], task_token: str | None = None
    ) -> None:
        event = parse_annotation_task_dispatched_event(detail)

        async def _process():
            async with self._session_factory() as session:
                return await run_annotation_task(
                    session,
                    self._publisher,
                    event,
                    step_functions_task_token=task_token,
                )

        result = await run_with_cost_cap_handling(
            self._session_factory,
            self._publisher,
            detail,
            _process,
        )

        if result is None:
            if task_token:
                from eventforge.services.step_functions import send_task_success

                send_task_success(
                    task_token,
                    {
                        "skipped": True,
                        "task_id": str(event.payload.task_id),
                        "task_index": event.payload.task_index,
                    },
                )
            logger.info(
                "Skipped duplicate annotation.task.dispatched",
                extra={
                    "event_id": str(event.event_id),
                    "job_id": str(event.job_id),
                    "correlation_id": event.correlation_id,
                    "task_index": event.payload.task_index,
                },
            )
            return

        logger.info(
            "Annotation task completed",
            extra={
                "event_id": str(event.event_id),
                "job_id": str(event.job_id),
                "correlation_id": event.correlation_id,
                "task_index": result.payload.task_index,
                "batch_id": str(result.payload.batch_id),
            },
        )


if __name__ == "__main__":
    main(AnnotationWorker, service_suffix="annotation")
