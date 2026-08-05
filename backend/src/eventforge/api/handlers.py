from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from eventforge.api.errors import AppError


def register_exception_handlers(app: FastAPI) -> None:
    """Register centralized API exception handlers on the FastAPI app."""

    @app.exception_handler(AppError)
    async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"message": exc.message, **exc.extra},
        )
