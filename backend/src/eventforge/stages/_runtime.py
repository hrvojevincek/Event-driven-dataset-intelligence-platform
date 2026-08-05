"""Shared runtime for pipeline stage handlers — idempotency, stage rows, publish rollback."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from eventforge.db.models import Job, JobStage, JobStageName
from eventforge.db.repositories import JobRepository, ProcessedEventRepository
from eventforge.db.repositories.job import JobStageRepository
from eventforge.events.publisher import EventPublisher, EventPublishError, PublishableEvent


class PipelineEvent(Protocol):
    """Minimal event shape required by stage handlers."""

    @property
    def event_id(self) -> uuid.UUID: ...

    @property
    def job_id(self) -> uuid.UUID: ...


@dataclass
class StageRun:
    """Per-event execution context: claim, project row, stage repo, and publish rollback."""

    session: AsyncSession
    publisher: EventPublisher | None
    processed_repo: ProcessedEventRepository
    stage_repo: JobStageRepository
    worker_name: str
    event_id: str
    project: Job

    @classmethod
    async def begin(
        cls,
        session: AsyncSession,
        publisher: EventPublisher | None,
        event: PipelineEvent,
        *,
        worker_name: str,
        claim: bool = True,
        project_label: str = "project",
        job_repo: JobRepository | None = None,
    ) -> StageRun | None:
        """Claim the event (optional) and load the project. Returns None when already processed."""
        processed_repo = ProcessedEventRepository(session)
        event_id = str(event.event_id)

        if claim and not await processed_repo.try_claim(event_id, worker_name):
            return None

        repo = job_repo or JobRepository(session)
        project = await repo.get_by_id(event.job_id)
        if project is None:
            msg = f"{project_label.capitalize()} not found for {worker_name}: {event.job_id}"
            raise ValueError(msg)

        return cls(
            session=session,
            publisher=publisher,
            processed_repo=processed_repo,
            stage_repo=JobStageRepository(session),
            worker_name=worker_name,
            event_id=event_id,
            project=project,
        )

    @classmethod
    async def wrap_claimed(
        cls,
        session: AsyncSession,
        publisher: EventPublisher,
        event: PipelineEvent,
        *,
        worker_name: str,
        project_label: str = "project",
        job_repo: JobRepository | None = None,
    ) -> StageRun:
        """Wrap an already-claimed event for publish rollback (no new claim)."""
        repo = job_repo or JobRepository(session)
        project = await repo.get_by_id(event.job_id)
        if project is None:
            msg = f"{project_label.capitalize()} not found for {worker_name}: {event.job_id}"
            raise ValueError(msg)
        return cls(
            session=session,
            publisher=publisher,
            processed_repo=ProcessedEventRepository(session),
            stage_repo=JobStageRepository(session),
            worker_name=worker_name,
            event_id=str(event.event_id),
            project=project,
        )

    async def require_stage(self, stage: JobStageName | str) -> JobStage:
        """Load the pipeline stage row or raise."""
        stage_name = stage.value if isinstance(stage, JobStageName) else stage
        row = await self.stage_repo.get_by_job_and_stage(self.project.id, stage_name)
        if row is None:
            msg = f"{stage_name} stage missing for project: {self.project.id}"
            raise ValueError(msg)
        return row

    async def mark_running(self, stage_row: JobStage) -> None:
        await self.stage_repo.mark_running(stage_row)

    async def mark_completed(self, stage_row: JobStage) -> None:
        await self.stage_repo.mark_completed(stage_row)

    async def commit(self) -> None:
        await self.session.commit()

    async def complete_stage(self, stage_row: JobStage) -> None:
        """Mark a stage completed and commit the transaction."""
        await self.mark_completed(stage_row)
        await self.commit()

    async def defer(self) -> None:
        """Release the idempotency claim so the event can be retried later."""
        await self.processed_repo.release_claim(self.event_id, self.worker_name)
        await self.commit()

    async def publish(self, event: PublishableEvent, *, source: str) -> None:
        """Publish one event; release the claim if EventBridge fails after commit."""
        if self.publisher is None:
            msg = "StageRun.publish requires a publisher"
            raise RuntimeError(msg)
        try:
            await self.publisher.publish(event, source=source)
        except EventPublishError:
            await self.processed_repo.release_claim(self.event_id, self.worker_name)
            await self.commit()
            raise

    async def publish_many(self, events: list[PublishableEvent], *, source: str) -> None:
        """Publish events in order; release the claim if any publish fails."""
        if self.publisher is None:
            msg = "StageRun.publish_many requires a publisher"
            raise RuntimeError(msg)
        try:
            for event in events:
                await self.publisher.publish(event, source=source)
        except EventPublishError:
            await self.processed_repo.release_claim(self.event_id, self.worker_name)
            await self.commit()
            raise


def parse_event[T: BaseModel](detail: dict, expected_detail_type: str, model: type[T]) -> T:
    """Validate an EventBridge detail dict into a typed pipeline event."""
    if detail.get("detail_type") != expected_detail_type:
        msg = f"Unexpected detail_type: {detail.get('detail_type')}"
        raise ValueError(msg)
    return model.model_validate(detail)
