import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from eventforge.db.models import Job, JobStage, StageStatus
from eventforge.db.repositories.base import BaseRepository


class JobRepository(BaseRepository):
    """Read and list dataset projects."""
    async def get_by_id(self, job_id: uuid.UUID) -> Job | None:
        result = await self.session.execute(
            select(Job)
            .where(Job.id == job_id)
            .options(selectinload(Job.stages), selectinload(Job.dataset_export))
        )
        return result.scalar_one_or_none()

    async def get_by_correlation_id(self, correlation_id: str) -> Job | None:
        result = await self.session.execute(
            select(Job)
            .where(Job.correlation_id == correlation_id)
            .options(selectinload(Job.stages))
        )
        return result.scalar_one_or_none()

    async def list_by_user_id(self, user_id: uuid.UUID) -> list[Job]:
        result = await self.session.execute(
            select(Job)
            .where(Job.user_id == user_id)
            .order_by(Job.created_at.desc(), Job.id.desc())
        )
        return list(result.scalars().all())

    async def delete_for_user(self, job_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        """Delete a job owned by the user. Returns False if not found or not owned."""
        result = await self.session.execute(
            select(Job).where(Job.id == job_id, Job.user_id == user_id)
        )
        job = result.scalar_one_or_none()
        if job is None:
            return False
        await self.session.delete(job)
        await self.session.flush()
        return True


class JobStageRepository(BaseRepository):
    """Track and update per-stage execution status on a job."""

    async def _emit_stage_event(self, job_stage: JobStage) -> None:
        from eventforge.services.stage_stream import publish_stage_event

        job = await JobRepository(self.session).get_by_id(job_stage.job_id)
        if job is None:
            return
        publish_stage_event(
            job.id,
            job.correlation_id,
            stage=job_stage.stage,
            status=job_stage.status,
            job_status=job.status,
            detail=job_stage.error_detail,
            duration_ms=job_stage.duration_ms,
        )

    async def get_by_job_and_stage(self, job_id: uuid.UUID, stage: str) -> JobStage | None:
        result = await self.session.execute(
            select(JobStage).where(JobStage.job_id == job_id, JobStage.stage == stage)
        )
        return result.scalar_one_or_none()

    async def mark_running(self, job_stage: JobStage) -> JobStage:
        now = datetime.now(tz=UTC)
        job_stage.status = StageStatus.RUNNING.value
        job_stage.started_at = now
        await self.session.flush()
        await self._emit_stage_event(job_stage)
        return job_stage

    async def mark_completed(self, job_stage: JobStage) -> JobStage:
        now = datetime.now(tz=UTC)
        job_stage.status = StageStatus.COMPLETED.value
        job_stage.completed_at = now
        if job_stage.started_at is not None:
            job_stage.duration_ms = int((now - job_stage.started_at).total_seconds() * 1000)
        await self.session.flush()
        await self._emit_stage_event(job_stage)
        return job_stage

    async def mark_failed(self, job_stage: JobStage, error_detail: str) -> JobStage:
        now = datetime.now(tz=UTC)
        job_stage.status = StageStatus.FAILED.value
        job_stage.error_detail = error_detail
        job_stage.completed_at = now
        if job_stage.started_at is not None:
            job_stage.duration_ms = int((now - job_stage.started_at).total_seconds() * 1000)
        await self.session.flush()
        await self._emit_stage_event(job_stage)
        return job_stage
