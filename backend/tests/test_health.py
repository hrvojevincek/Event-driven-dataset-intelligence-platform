from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from eventforge.main import app


@pytest.fixture
async def client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_health_returns_ok(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_health_ready_returns_ok_when_postgres_available(client: AsyncClient) -> None:
    with patch("eventforge.api.routes.health.check_postgres", new_callable=AsyncMock) as mock_check:
        response = await client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "checks": {"postgres": "ok"}}
    mock_check.assert_awaited_once()


async def test_health_ready_returns_503_when_postgres_unavailable(client: AsyncClient) -> None:
    with patch(
        "eventforge.api.routes.health.check_postgres",
        new_callable=AsyncMock,
        side_effect=ConnectionRefusedError("connection refused"),
    ):
        response = await client.get("/health/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert "postgres" in body["checks"]


async def test_api_v1_stub(client: AsyncClient) -> None:
    response = await client.get("/api/v1/")
    assert response.status_code == 200
    assert response.json() == {"message": "EventForge API v1"}


async def test_openapi_docs_available(client: AsyncClient) -> None:
    response = await client.get("/docs")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
