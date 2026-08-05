import json
import uuid
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from eventforge.api.deps import get_db
from eventforge.api.routes.queries import get_publisher
from eventforge.core.config import Settings
from eventforge.db.models import PIPELINE_STAGE_NAMES, Asset, Job, JobStage
from eventforge.db.repositories import ProcessedEventRepository
from eventforge.events.publisher import EventPublisher
from eventforge.events.schemas import ProjectSubmittedEvent
from eventforge.main import app


@pytest.fixture
def upload_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "uploads"
    root.mkdir()
    test_settings = Settings(upload_root=str(root))
    monkeypatch.setattr(
        "eventforge.services.project.get_settings",
        lambda: test_settings,
    )
    monkeypatch.setattr(
        "eventforge.services.storage.local.get_settings",
        lambda: test_settings,
    )
    return root


@pytest.fixture
async def client(db_session: AsyncSession, upload_root: Path) -> AsyncClient:
    mock_publisher = AsyncMock(spec=EventPublisher)

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_publisher] = lambda: mock_publisher
    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        ac.mock_publisher = mock_publisher  # type: ignore[attr-defined]
        yield ac

    app.dependency_overrides.clear()


async def test_create_project_stores_assets_and_publishes(
    client: AsyncClient,
    db_session: AsyncSession,
    upload_root: Path,
) -> None:
    response = await client.post(
        "/api/v1/projects",
        data={
            "name": "Support calls batch",
            "schema_template": "support_call",
            "domain": "support_calls",
        },
        files=[
            ("files", ("call_001.txt", b"Customer: I need a refund.", "text/plain")),
            ("files", ("call_002.txt", b"Agent: Happy to help.", "text/plain")),
        ],
    )

    assert response.status_code == 201
    body = response.json()
    job_id = uuid.UUID(body["job_id"])
    assert body["asset_count"] == 2
    assert body["correlation_id"]

    client.mock_publisher.publish_project_submitted.assert_awaited_once()  # type: ignore[attr-defined]
    published: ProjectSubmittedEvent = (
        client.mock_publisher.publish_project_submitted.await_args.args[0]  # type: ignore[attr-defined]
    )
    assert published.payload.name == "Support calls batch"
    assert published.payload.schema_template == "support_call"
    assert published.payload.asset_count == 2

    asset_count = await db_session.scalar(
        select(func.count()).select_from(Asset).where(Asset.job_id == job_id)
    )
    assert asset_count == 2

    stage_count = await db_session.scalar(
        select(func.count()).select_from(JobStage).where(JobStage.job_id == job_id)
    )
    assert stage_count == len(PIPELINE_STAGE_NAMES)

    job = await db_session.get(Job, job_id)
    assert job is not None
    schema = json.loads(job.schema_json)
    assert "emotion" in schema["properties"]

    project_dir = upload_root / str(job_id)
    assert project_dir.is_dir()
    assert (project_dir / "call_001.txt").read_text() == "Customer: I need a refund."


async def test_create_project_rejects_unsupported_extension(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/projects",
        data={"name": "Bad upload", "schema_template": "support_call"},
        files=[("files", ("virus.exe", b"bad", "application/octet-stream"))],
    )
    assert response.status_code == 422
    assert "Unsupported file type" in response.json()["detail"]["message"]


async def test_create_project_requires_schema(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/projects",
        data={"name": "No schema"},
        files=[("files", ("note.txt", b"hello", "text/plain"))],
    )
    assert response.status_code == 422
    assert "schema_template or schema_json" in response.json()["detail"]["message"]


async def test_create_project_publisher_claim_record(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    response = await client.post(
        "/api/v1/projects",
        data={"name": "Claim test", "schema_template": "support_call"},
        files=[("files", ("note.txt", b"hello", "text/plain"))],
    )
    assert response.status_code == 201

    published: ProjectSubmittedEvent = (
        client.mock_publisher.publish_project_submitted.await_args.args[0]  # type: ignore[attr-defined]
    )
    repo = ProcessedEventRepository(db_session)
    record = await repo.get_by_event_id(str(published.event_id))
    assert record is not None
    assert record.worker_name == "api"
