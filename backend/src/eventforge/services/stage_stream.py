"""In-process pub/sub for pipeline stage SSE events, keyed by job id."""

import asyncio
import json
import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from eventforge.api.schemas.stages import JobStageResponse
from eventforge.db.models import PIPELINE_STAGE_NAMES, Job, JobStatus
from eventforge.db.session import get_session_factory

_STAGE_ORDER = {stage.value: index for index, stage in enumerate(PIPELINE_STAGE_NAMES)}

StreamEventType = Literal["snapshot", "stage_update", "job_complete"]

SSE_KEEPALIVE_SECONDS = 15.0


class JobStreamEvent(BaseModel):
    """Payload emitted on the project SSE stream."""

    event: StreamEventType
    job_id: UUID
    correlation_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    job_status: str | None = None
    stage: str | None = None
    status: str | None = None
    detail: str | None = None
    duration_ms: int | None = None
    stages: list[JobStageResponse] | None = None


class StreamBroker:
    """Fan-out stage events to SSE subscribers within the same API process."""

    def __init__(self) -> None:
        self._subscribers: dict[str,
                                list[asyncio.Queue[JobStreamEvent | None]]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, key: str) -> asyncio.Queue[JobStreamEvent | None]:
        queue: asyncio.Queue[JobStreamEvent | None] = asyncio.Queue()
        async with self._lock:
            self._subscribers.setdefault(key, []).append(queue)
        return queue

    async def unsubscribe(self, key: str, queue: asyncio.Queue
                          [JobStreamEvent | None]) -> None:
        async with self._lock:
            queues = self._subscribers.get(key, [])
            if queue in queues:
                queues.remove(queue)
            if not queues:
                self._subscribers.pop(key, None)

    def publish(self, key: str, event: JobStreamEvent) -> None:
        for queue in self._subscribers.get(key, []):
            queue.put_nowait(event)


stream_broker = StreamBroker()


def publish_stage_event(
    job_id: UUID,
    correlation_id: str,
    *,
    stage: str,
    status: str,
    job_status: str | None = None,
    detail: str | None = None,
    duration_ms: int | None = None,
) -> None:
    """Notify in-process SSE subscribers of a stage transition."""
    stream_broker.publish(
        str(job_id),
        JobStreamEvent(
            event="stage_update",
            job_id=job_id,
            correlation_id=correlation_id,
            stage=stage,
            status=status,
            job_status=job_status,
            detail=detail,
            duration_ms=duration_ms,
        ),
    )


def format_sse_keepalive() -> str:
    """SSE comment frame to keep ALB/proxy connections alive between stage updates."""
    return ": keepalive\n\n"


def format_sse(event: JobStreamEvent, *, sse_event: str | None = None) -> str:
    """Serialize a stream event as a Server-Sent Events frame."""
    lines: list[str] = []
    if sse_event:
        lines.append(f"event: {sse_event}")
    lines.append(f"data: {event.model_dump_json()}")
    lines.append("")
    return "\n".join(lines) + "\n"


def _sorted_stages(job: Job) -> list:
    return sorted(job.stages, key=lambda stage: _STAGE_ORDER.get(
        stage.stage, len(_STAGE_ORDER)))


def _stage_responses(job: Job) -> list[JobStageResponse]:
    return [
        JobStageResponse(
            stage=stage.stage,
            status=stage.status,
            started_at=stage.started_at,
            completed_at=stage.completed_at,
            duration_ms=stage.duration_ms,
            error_detail=stage.error_detail,
        )
        for stage in _sorted_stages(job)
    ]


def _stage_fingerprint(job: Job) -> tuple[tuple[str, str, str | None, int | None], ...]:
    return tuple(
        (stage.stage, stage.status, stage.error_detail, stage.duration_ms)
        for stage in _sorted_stages(job)
    )


async def iter_job_stream_events(
    job_id: UUID,
    user_id: UUID,
) -> AsyncIterator[JobStreamEvent | None]:
    """Yield SSE events for a job, polling the DB and listening on the in-process broker."""
    from eventforge.db.repositories import JobRepository

    session_factory = get_session_factory()
    broker_key = str(job_id)
    queue = await stream_broker.subscribe(broker_key)
    last_fingerprint: tuple[tuple[str, str, str |
                                  None, int | None], ...] | None = None
    last_job_status: str | None = None
    last_yield_at = time.monotonic()

    try:
        poll_immediately = True
        while True:
            now = time.monotonic()
            if now - last_yield_at >= SSE_KEEPALIVE_SECONDS:
                yield None
                last_yield_at = now
                continue

            if not poll_immediately:
                wait_seconds = min(
                    1.0, SSE_KEEPALIVE_SECONDS - (now - last_yield_at))
                if wait_seconds > 0:
                    try:
                        await asyncio.wait_for(queue.get(), timeout=wait_seconds)
                    except TimeoutError:
                        pass
            poll_immediately = False

            async with session_factory() as session:
                job = await JobRepository(session).get_by_id(job_id)
                if job is None or job.user_id != user_id:
                    return

                fingerprint = _stage_fingerprint(job)
                stages = _stage_responses(job)

                if last_fingerprint is None:
                    yield JobStreamEvent(
                        event="snapshot",
                        job_id=job.id,
                        correlation_id=job.correlation_id,
                        job_status=job.status,
                        stages=stages,
                    )
                    last_yield_at = time.monotonic()
                elif fingerprint != last_fingerprint:
                    previous = {item[0]: item for item in last_fingerprint}
                    for stage_row in fingerprint:
                        stage_name, status, detail, duration_ms = stage_row
                        if previous.get(stage_name) != stage_row:
                            yield JobStreamEvent(
                                event="stage_update",
                                job_id=job.id,
                                correlation_id=job.correlation_id,
                                job_status=job.status,
                                stage=stage_name,
                                status=status,
                                detail=detail,
                                duration_ms=duration_ms,
                            )
                            last_yield_at = time.monotonic()

                if job.status != last_job_status and job.status in {
                    JobStatus.COMPLETED.value,
                    JobStatus.FAILED.value,
                }:
                    yield JobStreamEvent(
                        event="job_complete",
                        job_id=job.id,
                        correlation_id=job.correlation_id,
                        job_status=job.status,
                        stages=stages,
                    )
                    last_yield_at = time.monotonic()
                    return

                last_fingerprint = fingerprint
                last_job_status = job.status
    finally:
        await stream_broker.unsubscribe(broker_key, queue)


def parse_stream_event(raw: str) -> JobStreamEvent:
    """Parse a JSON SSE data payload (for tests)."""
    return JobStreamEvent.model_validate(json.loads(raw))
