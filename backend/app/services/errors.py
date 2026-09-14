class DomainError(Exception):
    """A domain rule was broken. Carries the HTTP status the API answers with."""

    status_code = 422

    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


class NotFound(DomainError):
    status_code = 404


class Conflict(DomainError):
    """The request contradicts something already recorded."""

    status_code = 409


class Invalid(DomainError):
    status_code = 422
