import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

from eventforge.core.aws import boto_client
from eventforge.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

SQS_POLL_ERROR_BACKOFF_SECONDS = 5.0
SQS_QUEUE_WAIT_INITIAL_SECONDS = 1.0
SQS_QUEUE_WAIT_MAX_SECONDS = 10.0


class SqsConsumer(ABC):
    """Long-poll an SQS queue and dispatch messages to handle_message."""

    def __init__(
        self,
        queue_name: str,
        settings: Settings | None = None,
        *,
        wait_time_seconds: int | None = None,
        max_messages: int | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._queue_name = queue_name
        self._wait_time_seconds = wait_time_seconds or self._settings.sqs_wait_time_seconds
        self._max_messages = max_messages or self._settings.sqs_max_messages
        self._client: Any | None = None
        self._queue_url: str | None = None

    @property
    def client(self) -> Any:
        if self._client is None:
            self._client = boto_client("sqs", self._settings)
        return self._client

    @property
    def queue_url(self) -> str:
        if self._queue_url is None:
            self._resolve_queue_url()
        return self._queue_url

    def _resolve_queue_url(self) -> str:
        response = self.client.get_queue_url(QueueName=self._queue_name)
        self._queue_url = response["QueueUrl"]
        return self._queue_url

    async def _wait_for_queue_ready(self) -> None:
        delay = SQS_QUEUE_WAIT_INITIAL_SECONDS
        while True:
            try:
                await asyncio.to_thread(self._resolve_queue_url)
                logger.info("SQS queue ready", extra={"queue": self._queue_name})
                return
            except (BotoCoreError, ClientError):
                logger.warning(
                    "Waiting for SQS queue (LocalStack init may still be running)",
                    extra={"queue": self._queue_name},
                )
                await asyncio.sleep(delay)
                delay = min(delay * 1.5, SQS_QUEUE_WAIT_MAX_SECONDS)

    async def run_forever(self) -> None:
        logger.info("Starting SQS consumer", extra={"queue": self._queue_name})
        await self._wait_for_queue_ready()
        while True:
            await self.poll_once()

    async def poll_once(self) -> int:
        messages, errored = await asyncio.to_thread(self._receive_messages)
        if errored:
            await asyncio.sleep(SQS_POLL_ERROR_BACKOFF_SECONDS)
            return 0
        for message in messages:
            receipt_handle = message["ReceiptHandle"]
            try:
                await self.handle_message(message)
            except Exception:
                logger.exception(
                    "Message handler failed; leaving on queue for retry",
                    extra={"message_id": message.get("MessageId")},
                )
                continue

            await asyncio.to_thread(self._delete_message, receipt_handle)
        return len(messages)

    def _receive_messages(self) -> tuple[list[dict[str, Any]], bool]:
        try:
            response = self.client.receive_message(
                QueueUrl=self.queue_url,
                MaxNumberOfMessages=self._max_messages,
                WaitTimeSeconds=self._wait_time_seconds,
                MessageAttributeNames=["All"],
                AttributeNames=["ApproximateReceiveCount"],
            )
        except (BotoCoreError, ClientError):
            # Transient SQS/network errors must not kill the consumer loop.
            # Back off in poll_once so we don't hammer LocalStack during init.
            logger.exception("SQS receive failed", extra={"queue": self._queue_name})
            self._queue_url = None
            return [], True
        return response.get("Messages", []), False

    def _delete_message(self, receipt_handle: str) -> None:
        try:
            self.client.delete_message(QueueUrl=self.queue_url, ReceiptHandle=receipt_handle)
        except (BotoCoreError, ClientError):
            # Delete failure means the message redelivers; idempotency guards
            # against double-processing. Log so the failure is visible.
            logger.exception(
                "SQS delete failed; message will redeliver",
                extra={"queue": self._queue_name},
            )

    @abstractmethod
    async def handle_message(self, message: dict[str, Any]) -> None:
        """Process one SQS message. Raise to leave the message for retry."""
