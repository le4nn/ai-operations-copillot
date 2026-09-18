"""Application exceptions and their stable public representation."""


class AppError(Exception):
    """Expected domain/application error safe to expose to an API client."""

    def __init__(self, *, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


class ResourceNotFoundError(AppError):
    def __init__(self, resource: str, resource_id: str | int) -> None:
        super().__init__(
            status_code=404,
            code="resource_not_found",
            message=f"{resource} with id '{resource_id}' was not found",
        )
