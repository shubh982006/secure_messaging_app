"""Typed application errors mapped to the API_CONTRACT error envelope.

Every non-2xx response is::

    { "error": { "code": "...", "message": "...", "detail": {} } }
"""

from typing import Any


class AppError(Exception):
    """Base class for every error the API deliberately returns."""

    status_code: int = 400
    code: str = "BAD_REQUEST"
    message: str = "Bad request"

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        status_code: int | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        self.message = message or self.message
        self.code = code or self.code
        self.status_code = status_code or self.status_code
        self.detail = detail or {}
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "detail": self.detail,
            }
        }


class ValidationError(AppError):
    status_code = 400
    code = "VALIDATION_ERROR"
    message = "Request failed validation"


class Unauthenticated(AppError):
    status_code = 401
    code = "UNAUTHENTICATED"
    message = "Missing or expired credentials"


class Forbidden(AppError):
    status_code = 403
    code = "FORBIDDEN"
    message = "You do not have access to this resource"


class NotFound(AppError):
    status_code = 404
    code = "NOT_FOUND"
    message = "Resource not found"


class UserNotFound(NotFound):
    code = "USER_NOT_FOUND"
    message = "User not found"


class ConversationNotFound(NotFound):
    code = "CONVERSATION_NOT_FOUND"
    message = "Conversation not found"


class MessageNotFound(NotFound):
    code = "MESSAGE_NOT_FOUND"
    message = "Message not found"


class ContactNotFound(NotFound):
    code = "CONTACT_NOT_FOUND"
    message = "Contact not found"


class Conflict(AppError):
    status_code = 409
    code = "CONFLICT"
    message = "Resource already exists"


class Unprocessable(AppError):
    status_code = 422
    code = "UNPROCESSABLE"
    message = "Request could not be processed"


class RateLimited(AppError):
    status_code = 429
    code = "RATE_LIMITED"
    message = "Too many messages, slow down"
