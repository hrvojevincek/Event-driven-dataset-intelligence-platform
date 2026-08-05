from collections.abc import AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from eventforge.core.config import Settings, get_settings
from eventforge.db.models import User
from eventforge.db.repositories import UserRepository
from eventforge.db.session import get_session
from eventforge.events.publisher import EventPublisher

__all__ = ["Settings", "get_current_user", "get_db", "get_publisher", "get_settings"]


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async for session in get_session():
        yield session


async def get_current_user(session: AsyncSession = Depends(get_db)) -> User:
    """Resolve the implicit local mock user for all API requests."""
    return await UserRepository(session).get_or_create_mock_user()


def get_publisher(
    settings: Settings = Depends(get_settings),
) -> EventPublisher:
    return EventPublisher(settings)
