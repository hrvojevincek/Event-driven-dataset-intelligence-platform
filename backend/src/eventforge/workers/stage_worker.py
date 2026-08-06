"""Shared wiring for pipeline stage SQS workers."""

from __future__ import annotations

import logging
from abc import abstractmethod
from typing import Any, ClassVar

from eventforge.core.config import Settings, get_settings
from eventforge.db.session import get_session_factory
from eventforge.events.parser import parse_eventbridge_sqs_body
from eventforge.events.publisher import EventPublisher
from eventforge.services.pipeline_failure import parse_failed_event_detail, process_pipeline_failure
from eventforge.workers.base import SqsConsumer

logger = logging.getLogger(__name__)

# Business/config failures — mark job failed and ack. Other exceptions retry → DLQ.
_TERMINAL_EXCEPTIONS = (ValueError, RuntimeError)


class StageWorker(SqsConsumer):
    """SQS consumer with DB session, publisher, and terminal-failure recording.

    Subclasses implement ``process_message``. ``ValueError`` / ``RuntimeError`` are
    treated as terminal: persist ``pipeline.failed``, update Job/JobStage, ack the
    message. Unexpected exceptions still leave the message for SQS retry → DLQ.
    """

    worker_name: ClassVar[str]
    event_source: ClassVar[str]
    record_terminal_failures: ClassVar[bool] = True

    def __init__(self, queue_name: str, settings: Settings | None = None) -> None:
        settings = settings or get_settings()
        super().__init__(queue_name, settings)
        self._publisher = EventPublisher(settings)
        self._session_factory = get_session_factory(settings)

    async def handle_message(self, message: dict[str, Any]) -> None:
        if not self.record_terminal_failures:
            await self.process_message(message)
            return
        try:
            await self.process_message(message)
        except _TERMINAL_EXCEPTIONS as exc:
            await self._record_terminal_failure(message, exc)

    @abstractmethod
    async def process_message(self, message: dict[str, Any]) -> None:
        """Process one stage message. Raise ``ValueError``/``RuntimeError`` for terminal fail."""

    async def _record_terminal_failure(
        self,
        message: dict[str, Any],
        exc: BaseException,
    ) -> None:
        """Mark the job/stage failed from a fresh session and emit pipeline.failed."""
        try:
            detail = parse_eventbridge_sqs_body(message["Body"])
            failed_event = parse_failed_event_detail(detail)
        except ValueError:
            logger.exception(
                "Terminal failure but SQS body is not a valid event; leaving for retry/DLQ",
                extra={"message_id": message.get("MessageId"), "worker": self.worker_name},
            )
            raise exc from None

        receive_count_raw = message.get("Attributes", {}).get("ApproximateReceiveCount")
        receive_count = int(receive_count_raw) if receive_count_raw else None

        try:
            async with self._session_factory() as session:
                result = await process_pipeline_failure(
                    session,
                    self._publisher,
                    failed_event=failed_event,
                    error_message=str(exc),
                    source_queue=self._queue_name,
                    receive_count=receive_count,
                    claim_worker_name=self.worker_name,
                    publish_source=self.event_source,
                )
        except Exception:
            logger.exception(
                "Failed to persist terminal pipeline failure; leaving message for retry",
                extra={
                    "message_id": message.get("MessageId"),
                    "worker": self.worker_name,
                    "job_id": str(failed_event.job_id),
                },
            )
            raise exc from None

        if result is None:
            logger.info(
                "Skipped duplicate terminal failure",
                extra={
                    "event_id": str(failed_event.event_id),
                    "job_id": str(failed_event.job_id),
                    "worker": self.worker_name,
                },
            )
            return

        logger.error(
            "Stage failed terminally; job marked failed",
            extra={
                "event_id": str(failed_event.event_id),
                "job_id": str(failed_event.job_id),
                "correlation_id": failed_event.correlation_id,
                "stage": result.payload.stage,
                "error": str(exc),
                "worker": self.worker_name,
            },
        )
