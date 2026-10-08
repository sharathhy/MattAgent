class ServiceError(Exception):
    """Base error for business-rule violations; carries an HTTP-friendly status code."""

    status_code = 400

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFoundError(ServiceError):
    status_code = 404


class ConflictError(ServiceError):
    status_code = 409


class ForbiddenError(ServiceError):
    status_code = 403
