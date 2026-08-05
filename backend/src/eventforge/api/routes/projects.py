import json
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from eventforge.api.deps import get_current_user, get_db, get_publisher, get_settings
from eventforge.api.schemas.projects import (
    ProjectDetailResponse,
    ProjectSummaryResponse,
    SubmitProjectResponse,
)
from eventforge.core.config import Settings
from eventforge.db.models import User
from eventforge.db.repositories import DatasetExportRepository, ProjectRepository
from eventforge.events.publisher import EventPublisher, EventPublishError
from eventforge.services.project import (
    UploadPayload,
    delete_project,
    get_project_detail,
    list_projects,
    submit_project,
)

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


@router.get("/projects", response_model=list[ProjectSummaryResponse])
async def list_user_projects(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ProjectSummaryResponse]:
    return await list_projects(db, current_user)


@router.get("/projects/{project_id}", response_model=ProjectDetailResponse)
async def get_project(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProjectDetailResponse:
    detail = await get_project_detail(db, project_id, current_user)
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Project not found"},
        )
    return detail


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_project(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    deleted = await delete_project(db, project_id, current_user)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Project not found"},
        )


@router.get("/projects/{project_id}/export")
async def download_project_export(
    project_id: uuid.UUID,
    format: str = "jsonl",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    project = await ProjectRepository(db).get_by_id(project_id)
    if project is None or project.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Project not found"},
        )

    export = await DatasetExportRepository(db).get_by_job_id(project_id)
    if export is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Export not ready"},
        )

    if format == "qc":
        return JSONResponse(content=json.loads(export.qc_report_json))

    if format != "jsonl":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "format must be 'jsonl' or 'qc'"},
        )

    return Response(
        content=export.export_content,
        media_type="application/x-ndjson",
        headers={
            "Content-Disposition": f'attachment; filename="project-{project_id}.jsonl"',
        },
    )
