"""HTTP-facing application errors mapped by the global exception handler."""


class AppError(Exception):
    """Base API error with an HTTP status code and JSON response body."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 400,
        extra: dict | None = None,
    ) -> None:
        self.message = message
        self.status_code = status_code
        self.extra = extra or {}
        super().__init__(message)


class NotFoundError(AppError):
    """Resource was not found or is not accessible to the caller."""

    def __init__(self, message: str = "Not found") -> None:
        super().__init__(message, status_code=404)


class ValidationAppError(AppError):
    """Request or domain input failed validation."""

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=422)


class UpstreamError(AppError):
    """An upstream dependency failed while handling the request."""

    def __init__(self, message: str, *, error: str | None = None) -> None:
        extra = {"error": error} if error else {}
        super().__init__(message, status_code=502, extra=extra)


class ServiceUnavailableError(AppError):
    """A required dependency is unavailable."""

    def __init__(self, message: str, *, extra: dict | None = None) -> None:
        super().__init__(message, status_code=503, extra=extra)
