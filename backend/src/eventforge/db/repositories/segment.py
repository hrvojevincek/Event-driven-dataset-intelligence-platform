import uuid

from sqlalchemy import select

from eventforge.db.models import Segment
from eventforge.db.repositories.base import BaseRepository


class SegmentRepository(BaseRepository):
    """Relational access for preprocessed text segments."""

    async def list_by_job_id(self, job_id: uuid.UUID) -> list[Segment]:
        result = await self.session.execute(
            select(Segment)
            .where(Segment.job_id == job_id)
            .order_by(Segment.asset_id, Segment.segment_index)
        )
        return list(result.scalars().all())

    async def list_by_ids(self, segment_ids: list[uuid.UUID]) -> list[Segment]:
        if not segment_ids:
            return []
        result = await self.session.execute(select(Segment).where(Segment.id.in_(segment_ids)))
        return list(result.scalars().all())

    async def search_similar(
        self,
        job_id: uuid.UUID,
        query_vector: list[float],
        *,
        limit: int = 10,
    ) -> list[Segment]:
        """Legacy RAG compat — returns job segments in order until planning stage lands."""
        _ = query_vector
        segments = await self.list_by_job_id(job_id)
        return segments[:limit]
