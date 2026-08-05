"""Shared wiring for pipeline stage SQS workers."""

from eventforge.core.config import Settings, get_settings
from eventforge.db.session import get_session_factory
from eventforge.events.publisher import EventPublisher
from eventforge.workers.base import SqsConsumer


class StageWorker(SqsConsumer):
    """SQS consumer with a DB session factory and EventBridge publisher."""

    def __init__(self, queue_name: str, settings: Settings | None = None) -> None:
        settings = settings or get_settings()
        super().__init__(queue_name, settings)
        self._publisher = EventPublisher(settings)
        self._session_factory = get_session_factory(settings)
