from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from eventforge.api.deps import get_current_user, get_db
from eventforge.db.models import User
from eventforge.db.repositories import JobRepository
from eventforge.services.stage_stream import (
    format_sse,
    format_sse_keepalive,
    iter_job_stream_events,
)

router = APIRouter()


async def _assert_job_access(
    db: AsyncSession,
    job_id: UUID,
    user: User,
) -> None:
    job = await JobRepository(db).get_by_id(job_id)
    if job is None or job.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")


@router.get("/projects/{project_id}/stream")
async def stream_project_events(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Stream pipeline stage updates for a job via Server-Sent Events."""
    await _assert_job_access(db, project_id, current_user)
    user_id = current_user.id

    async def event_generator():
        async for event in iter_job_stream_events(project_id, user_id):
            if event is None:
                yield format_sse_keepalive()
            else:
                yield format_sse(event, sse_event=event.event)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
