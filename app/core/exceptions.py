from __future__ import annotations

import logging
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class AppException(Exception):
    """Base exception for the application."""

    def __init__(
        self,
        message: str,
        status_code: int = HTTPStatus.BAD_REQUEST,
        code: str = "BAD_REQUEST",
        details: Any = None,
    ) -> None:
        self.message = message
        self.status_code = status_code
        self.code = code
        self.details = details
        super().__init__(message)


class ValidationException(AppException):
    """Raised when request validation fails."""

    def __init__(
        self,
        message: str,
        code: str = "VALIDATION_ERROR",
        details: Any = None,
    ) -> None:
        super().__init__(
            message=message,
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            code=code,
            details=details,
        )


class AuthenticationException(AppException):
    """Raised when authentication fails."""

    def __init__(
        self,
        message: str = "Authentication failed",
        code: str = "AUTHENTICATION_FAILED",
        details: Any = None,
    ) -> None:
        super().__init__(
            message=message,
            status_code=HTTPStatus.UNAUTHORIZED,
            code=code,
            details=details,
        )


class UnauthorizedException(AuthenticationException):
    """Raised when an unauthorized user attempts an operation."""

    def __init__(
        self,
        message: str = "Unauthorized",
        code: str = "UNAUTHORIZED",
        details: Any = None,
    ) -> None:
        super().__init__(
            message=message,
            code=code,
            details=details,
        )


class ForbiddenException(AppException):
    """Raised when access to a resource is forbidden."""

    def __init__(
        self,
        message: str = "Forbidden",
        code: str = "FORBIDDEN",
        details: Any = None,
    ) -> None:
        super().__init__(
            message=message,
            status_code=HTTPStatus.FORBIDDEN,
            code=code,
            details=details,
        )


class NotFoundException(AppException):
    """Raised when a requested resource is not found."""

    def __init__(
        self,
        message: str = "Resource not found",
        code: str = "NOT_FOUND",
        details: Any = None,
    ) -> None:
        super().__init__(
            message=message,
            status_code=HTTPStatus.NOT_FOUND,
            code=code,
            details=details,
        )


class ResourceNotFoundException(NotFoundException):
    """Alias for NotFoundException."""


class AccountNotFoundException(NotFoundException):
    """Raised when an account is not found."""

    def __init__(
        self,
        message: str = "Account not found",
        code: str = "ACCOUNT_NOT_FOUND",
        details: Any = None,
    ) -> None:
        super().__init__(
            message=message,
            code=code,
            details=details,
        )


class ConflictException(AppException):
    """Raised when a resource state conflicts with the request."""

    def __init__(
        self,
        message: str,
        code: str = "CONFLICT",
        details: Any = None,
    ) -> None:
        super().__init__(
            message=message,
            status_code=HTTPStatus.CONFLICT,
            code=code,
            details=details,
        )


class DuplicateTransactionException(ConflictException):
    """Raised when a duplicate reference ID is provided for the same account."""

    def __init__(
        self,
        message: str = "Duplicate transaction reference.",
        code: str = "DUPLICATE_TRANSACTION",
        details: Any = None,
    ) -> None:
        super().__init__(
            message=message,
            code=code,
            details=details,
        )


class InsufficientBalanceException(AppException):
    """Raised when an account has insufficient funds for a debit."""

    def __init__(
        self,
        message: str = "The account has insufficient funds for this debit.",
        code: str = "INSUFFICIENT_BALANCE",
        details: Any = None,
    ) -> None:
        super().__init__(
            message=message,
            status_code=HTTPStatus.CONFLICT,
            code=code,
            details=details,
        )


class DatabaseException(AppException):
    """Raised when a database operation fails."""

    def __init__(
        self,
        message: str = "Database operation failed",
        code: str = "DATABASE_ERROR",
        details: Any = None,
    ) -> None:
        super().__init__(
            message=message,
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            code=code,
            details=details,
        )


async def app_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle AppException and return structured JSON response."""
    assert isinstance(exc, AppException)

    if exc.status_code >= 500:
        logger.error(
            "Application error [%s]: %s",
            exc.code,
            exc.message,
            extra={"path": request.url.path, "status_code": exc.status_code},
        )
    else:
        logger.warning(
            "Application error [%s]: %s",
            exc.code,
            exc.message,
            extra={"path": request.url.path, "status_code": exc.status_code},
        )

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            },
        },
    )


async def validation_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Handle FastAPI / Pydantic RequestValidationError."""
    assert isinstance(exc, RequestValidationError)
    logger.warning(
        "Validation error on %s: %s",
        request.url.path,
        exc.errors(),
        extra={"path": request.url.path},
    )
    return JSONResponse(
        status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed",
                "details": exc.errors(),
            },
        },
    )


async def starlette_http_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Handle Starlette / FastAPI HTTPException."""
    assert isinstance(exc, StarletteHTTPException)
    code = "HTTP_ERROR"
    if exc.status_code == HTTPStatus.NOT_FOUND:
        code = "NOT_FOUND"
    elif exc.status_code == HTTPStatus.METHOD_NOT_ALLOWED:
        code = "METHOD_NOT_ALLOWED"
    elif exc.status_code == HTTPStatus.UNAUTHORIZED:
        code = "UNAUTHORIZED"
    elif exc.status_code == HTTPStatus.FORBIDDEN:
        code = "FORBIDDEN"

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": code,
                "message": str(exc.detail),
                "details": None,
            },
        },
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected exceptions with a safe JSON envelope."""
    logger.exception(
        "Unhandled exception: %s",
        str(exc),
        extra={"path": request.url.path},
    )
    return JSONResponse(
        status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "Internal server error",
                "details": None,
            },
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register application exception handlers."""
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(StarletteHTTPException, starlette_http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
