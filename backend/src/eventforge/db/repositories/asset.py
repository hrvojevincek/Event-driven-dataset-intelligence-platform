import uuid

from sqlalchemy import select

from eventforge.db.models import Asset
from eventforge.db.repositories.base import BaseRepository


class AssetRepository(BaseRepository):
    """Access uploaded assets for a project."""

    async def list_by_job_id(self, job_id: uuid.UUID) -> list[Asset]:
        result = await self.session.execute(
            select(Asset).where(Asset.job_id == job_id).order_by(Asset.created_at)
        )
        return list(result.scalars().all())

    async def list_by_ids(self, asset_ids: list[uuid.UUID]) -> list[Asset]:
        if not asset_ids:
            return []
        result = await self.session.execute(select(Asset).where(Asset.id.in_(asset_ids)))
        return list(result.scalars().all())
