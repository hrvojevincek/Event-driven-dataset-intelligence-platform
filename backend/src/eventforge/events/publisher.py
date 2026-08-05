import asyncio
import logging
from typing import Any, Protocol

from botocore.exceptions import BotoCoreError, ClientError

from eventforge.core.aws import boto_client
from eventforge.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

EVENT_SOURCE_API = "eventforge.api"
EVENT_SOURCE_INTAKE = "eventforge.workers.intake"
EVENT_SOURCE_PREPROCESSING = "eventforge.workers.preprocessing"
EVENT_SOURCE_PLANNING = "eventforge.workers.planning"
EVENT_SOURCE_ANNOTATION = "eventforge.workers.annotation"
EVENT_SOURCE_EXPORT = "eventforge.workers.export"
EVENT_SOURCE_DLQ = "eventforge.workers.dlq"
# Legacy event sources (same workers until Phases 3–7)
EVENT_SOURCE_INGESTION = EVENT_SOURCE_INTAKE
EVENT_SOURCE_EMBEDDING = EVENT_SOURCE_PREPROCESSING
EVENT_SOURCE_KNOWLEDGE = EVENT_SOURCE_PLANNING
EVENT_SOURCE_RESEARCH = EVENT_SOURCE_ANNOTATION
EVENT_SOURCE_SYNTHESIS = EVENT_SOURCE_EXPORT
PUBLISHER_WORKER_NAME = "api"


class EventPublishError(Exception):
    """Raised when EventBridge PutEvents fails."""


class PublishableEvent(Protocol):
    """Minimal interface for events sent to EventBridge."""
    @property
    def detail_type(self) -> str: ...

    def model_dump_json(self) -> str: ...


class EventPublisher:
    """Publishes pipeline events to the EventBridge bus."""
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._client: Any | None = None

    @property
    def client(self) -> Any:
        if self._client is None:
            self._client = boto_client("events", self._settings)
        return self._client

    async def publish_project_submitted(self, event: PublishableEvent) -> None:
        await self.publish(event, source=EVENT_SOURCE_API)

    async def publish_query_submitted(self, event: PublishableEvent) -> None:
        """Legacy alias — use publish_project_submitted after Phase 3."""
        await self.publish_project_submitted(event)

    async def publish(self, event: PublishableEvent, *, source: str) -> None:
        await asyncio.to_thread(self._publish_sync, event, source)

    def _publish_sync(self, event: PublishableEvent, source: str) -> None:
        try:
            response = self.client.put_events(
                Entries=[
                    {
                        "Source": source,
                        "DetailType": event.detail_type,
                        "Detail": event.model_dump_json(),
                        "EventBusName": self._settings.event_bus_name,
                    }
                ]
            )
        except (BotoCoreError, ClientError) as exc:
            logger.exception(
                "EventBridge publish failed",
                extra={"detail_type": event.detail_type},
            )
            raise EventPublishError(str(exc)) from exc

        failed = response.get("FailedEntryCount", 0)
        if failed:
            entry = response.get("Entries", [{}])[0]
            error_code = entry.get("ErrorCode", "Unknown")
            error_message = entry.get("ErrorMessage", "PutEvents failed")
            raise EventPublishError(f"{error_code}: {error_message}")

        logger.info(
            "Published event",
            extra={"detail_type": event.detail_type, "source": source},
        )
