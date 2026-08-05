from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from eventforge.api.deps import get_current_user, get_db, get_settings
from eventforge.api.schemas.queries import (
    QueryDetailResponse,
    QuerySummaryResponse,
    SubmitQueryRequest,
    SubmitQueryResponse,
)
from eventforge.core.config import Settings
from eventforge.db.models import User
from eventforge.events.publisher import EventPublisher, EventPublishError
from eventforge.services.query import (
    delete_query,
    get_query_detail,
    list_queries,
    submit_query,
)

router = APIRouter()


def get_publisher(
    settings: Settings = Depends(get_settings),
) -> EventPublisher:
    return EventPublisher(settings)


@router.post(
    "/queries",
    status_code=status.HTTP_201_CREATED,
    response_model=SubmitQueryResponse,
)
async def create_query(
    body: SubmitQueryRequest,
    db: AsyncSession = Depends(get_db),
    publisher: EventPublisher = Depends(get_publisher),
    current_user: User = Depends(get_current_user),
) -> SubmitQueryResponse:
    try:
        result = await submit_query(
            db,
            publisher,
            current_user,
            topic=body.topic,
            depth=body.depth,
            max_sources=body.max_sources,
        )
    except EventPublishError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "message": "Failed to publish query.submitted event",
                "error": str(exc),
            },
        ) from exc

    return SubmitQueryResponse(
        job_id=result.job_id, correlation_id=result.correlation_id
    )


@router.get(
    "/queries",
    response_model=list[QuerySummaryResponse],
)
async def list_user_queries(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[QuerySummaryResponse]:
    return await list_queries(db, current_user)


@router.get(
    "/queries/{job_id}",
    response_model=QueryDetailResponse,
)
async def get_query(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> QueryDetailResponse:
    detail = await get_query_detail(db, job_id, current_user)
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Job not found"
        )
    return detail


@router.delete(
    "/queries/{job_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_query(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    deleted = await delete_query(db, job_id, current_user)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Job not found"
        )
