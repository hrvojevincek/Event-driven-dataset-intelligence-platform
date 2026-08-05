import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from eventforge.api.deps import get_current_user, get_db, get_settings
from eventforge.api.routes.queries import get_publisher
from eventforge.api.schemas.projects import SubmitProjectResponse
from eventforge.core.config import Settings
from eventforge.db.models import User
from eventforge.events.publisher import EventPublisher, EventPublishError
from eventforge.services.project import UploadPayload, submit_project

router = APIRouter()


@router.post(
    "/projects",
    status_code=status.HTTP_201_CREATED,
    response_model=SubmitProjectResponse,
)
async def create_project(
    name: str = Form(..., min_length=1),
    files: list[UploadFile] = File(...),
    schema_template: str | None = Form(default=None),
    schema_json_override: str | None = Form(default=None),
    domain: str = Form(default="documents"),
    db: AsyncSession = Depends(get_db),
    publisher: EventPublisher = Depends(get_publisher),
    current_user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> SubmitProjectResponse:
    parsed_schema: dict | None = None
    if schema_json_override:
        try:
            loaded = json.loads(schema_json_override)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"message": "schema_json must be valid JSON"},
            ) from exc
        if not isinstance(loaded, dict):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"message": "schema_json must be a JSON object"},
            )
        parsed_schema = loaded

    uploads: list[UploadPayload] = []
    for upload in files:
        content = await upload.read()
        uploads.append(
            UploadPayload(
                filename=upload.filename or "upload.bin",
                content=content,
            )
        )

    try:
        result = await submit_project(
            db,
            publisher,
            current_user,
            name=name,
            uploads=uploads,
            schema_template=schema_template,
            schema_json=parsed_schema,
            domain=domain,
        )
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": str(exc)},
        ) from exc
    except EventPublishError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "message": "Failed to publish project.submitted event",
                "error": str(exc),
            },
        ) from exc

    return SubmitProjectResponse(
        job_id=result.job_id,
        correlation_id=result.correlation_id,
        asset_count=result.asset_count,
    )
