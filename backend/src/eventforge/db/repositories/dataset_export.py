import uuid

from sqlalchemy import select

from eventforge.db.models import DatasetExport
from eventforge.db.repositories.base import BaseRepository


class DatasetExportRepository(BaseRepository):
    """Access the final dataset export for a project."""

    async def get_by_job_id(self, job_id: uuid.UUID) -> DatasetExport | None:
        result = await self.session.execute(
            select(DatasetExport).where(DatasetExport.job_id == job_id)
        )
        return result.scalar_one_or_none()
