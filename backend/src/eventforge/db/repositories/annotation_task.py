import uuid

from sqlalchemy import select

from eventforge.db.models import AnnotationTask
from eventforge.db.repositories.base import BaseRepository


class AnnotationTaskRepository(BaseRepository):
    """Access annotation tasks planned for a project."""

    async def list_by_job_id(self, job_id: uuid.UUID) -> list[AnnotationTask]:
        result = await self.session.execute(
            select(AnnotationTask)
            .where(AnnotationTask.job_id == job_id)
            .order_by(AnnotationTask.task_index)
        )
        return list(result.scalars().all())

    async def list_by_ids(self, task_ids: list[uuid.UUID]) -> list[AnnotationTask]:
        if not task_ids:
            return []
        result = await self.session.execute(
            select(AnnotationTask).where(AnnotationTask.id.in_(task_ids))
        )
        return list(result.scalars().all())
