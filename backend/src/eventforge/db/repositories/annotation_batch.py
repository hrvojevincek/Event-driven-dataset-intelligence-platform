import uuid

from sqlalchemy import func, select

from eventforge.db.models import AnnotationBatch
from eventforge.db.repositories.base import BaseRepository


class AnnotationBatchRepository(BaseRepository):
    """Access labeled annotation batches for a project."""

    async def list_by_job_id(self, job_id: uuid.UUID) -> list[AnnotationBatch]:
        result = await self.session.execute(
            select(AnnotationBatch)
            .where(AnnotationBatch.job_id == job_id)
            .order_by(AnnotationBatch.task_index)
        )
        return list(result.scalars().all())

    async def get_by_task_id(self, task_id: uuid.UUID) -> AnnotationBatch | None:
        result = await self.session.execute(
            select(AnnotationBatch).where(AnnotationBatch.task_id == task_id)
        )
        return result.scalar_one_or_none()

    async def count_by_job_id(self, job_id: uuid.UUID) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(AnnotationBatch).where(
                AnnotationBatch.job_id == job_id
            )
        )
        return int(result.scalar_one())
