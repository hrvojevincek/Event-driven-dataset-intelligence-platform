import logging
from typing import Any

from eventforge.agents.knowledge import (
    parse_embedding_completed_event,
    process_embedding_completed,
)
from eventforge.core.config import get_settings
from eventforge.db.session import get_session_factory
from eventforge.events.parser import parse_eventbridge_sqs_body
from eventforge.events.publisher import EventPublisher
from eventforge.workers.base import SqsConsumer
from eventforge.workers.bootstrap import main
from eventforge.workers.cost_cap import run_with_cost_cap_handling

logger = logging.getLogger(__name__)


class KnowledgeWorker(SqsConsumer):
    """Consumes embedding.completed events and runs the knowledge mining agent."""

    def __init__(self) -> None:
        settings = get_settings()
        super().__init__(settings.knowledge_mining_queue_name, settings)
        self._publisher = EventPublisher(settings)
        self._session_factory = get_session_factory(settings)

    async def handle_message(self, message: dict[str, Any]) -> None:
        detail = parse_eventbridge_sqs_body(message["Body"])
        event = parse_embedding_completed_event(detail)

        async def _process():
            async with self._session_factory() as session:
                return await process_embedding_completed(
                    session, self._publisher, event
                )

        result = await run_with_cost_cap_handling(
            self._session_factory,
            self._publisher,
            detail,
            _process,
        )

        if result is None:
            logger.info(
                "Skipped duplicate embedding.completed",
                extra={
                    "event_id": str(event.event_id),
                    "job_id": str(event.job_id),
                    "correlation_id": event.correlation_id,
                },
            )
            return

        logger.info(
            "Knowledge mining completed",
            extra={
                "event_id": str(event.event_id),
                "job_id": str(event.job_id),
                "correlation_id": event.correlation_id,
                "entity_count": result.payload.entity_count,
            },
        )


if __name__ == "__main__":
    main(KnowledgeWorker, service_suffix="knowledge")
