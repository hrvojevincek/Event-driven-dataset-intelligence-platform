from fastapi import APIRouter, Depends

from eventforge.api.deps import Settings, get_settings
from eventforge.api.errors import ServiceUnavailableError
from eventforge.core.database import check_postgres

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
async def health_ready(settings: Settings = Depends(get_settings)) -> dict[str, object]:
    try:
        await check_postgres(settings)
    except Exception as exc:
        raise ServiceUnavailableError(
            "Service not ready",
            extra={"status": "not_ready", "checks": {"postgres": str(exc)}},
        ) from exc

    return {"status": "ready", "checks": {"postgres": "ok"}}
